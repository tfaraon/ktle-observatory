#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pluies saisonnieres sur le bassin du lac Eyre, annee par annee.

Donne le contexte climatique d'une crue : combien il est tombe sur le
bassin, saison par saison, sur toute la periode disponible, et ou se
situe une annee donnee dans cette distribution.

La source est SILO, la meme que celle qu'utilise deja la chaine du site
pour la pluie des trente derniers jours : grilles au cinquantieme de
degre, quotidiennes depuis 1889, ouvertes et sans inscription. Trois
dispositions du seau sont essayees dans l'ordre du moins couteux au
plus couteux, mensuelle, annuelle, puis quotidienne, et le script dit
laquelle il a trouvee. Pour cinquante ans, la difference est celle
entre six cents fichiers et vingt mille.

L'emprise se donne en GeoJSON ou directement en shapefile : la
geometrie d'un .shp se lit sans bibliotheque tierce et sans ses
fichiers annexes, seul le systeme de coordonnees leur est confie. Le
contour est donc suppose en degres WGS84, ce que le script verifie.

Les moyennes de bassin sont mises en cache par mois. Un second passage
ne retelecharge rien, et changer la definition des saisons ne coute
plus que le reassemblage.

    python tools/basin_rainfall.py --basin bassin.shp
    python tools/basin_rainfall.py --basin bassin.geojson --from 1972
    python tools/basin_rainfall.py --seasons "warm=10-3,cool=4-9"

Depuis un interpreteur :

    import basin_rainfall as br
    table = br.run(basin="bassin.shp", first=1972, last=2025)
    table["warm"][2025]
"""

import argparse
import json
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "rain_basin_cache"
USER_AGENT = ("ktle-observatory/1.0 (research; "
              "github.com/tfaraon/ktle-observatory)")

BASE = "https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official"
# Du moins couteux au plus couteux. Le premier qui repond est retenu.
LAYOUTS = [
    ("monthly", BASE + "/monthly/monthly_rain/{y}/{y}{m:02d}.monthly_rain.tif"),
    ("annual",  BASE + "/annual/daily_rain/{y}.daily_rain.nc"),
    ("daily",   BASE + "/daily/daily_rain/{y}/{y}{m:02d}{d:02d}.daily_rain.tif"),
]

SEASONS = {"warm": (10, 11, 12, 1, 2, 3), "cool": (4, 5, 6, 7, 8, 9)}


# ── Emprise ─────────────────────────────────────────────────

def read_shapefile(path):
    """Les anneaux d'un .shp de polygones, sans ses fichiers annexes.

    Le .shp porte la geometrie a lui seul ; .shx n'est qu'un index et
    .dbf les attributs. Le .prj manquant, les coordonnees sont
    verifiees plus bas plutot que supposees.
    """
    b = Path(path).read_bytes()
    if struct.unpack(">i", b[0:4])[0] != 9994:
        raise ValueError(f"{path} : ce n'est pas un shapefile")
    pos, rings = 100, []
    while pos < len(b):
        _, clen = struct.unpack(">ii", b[pos:pos + 8])
        body = b[pos + 8:pos + 8 + clen * 2]
        pos += 8 + clen * 2
        if struct.unpack("<i", body[0:4])[0] != 5:
            continue
        nparts, npts = struct.unpack("<ii", body[36:44])
        parts = struct.unpack(f"<{nparts}i", body[44:44 + 4 * nparts])
        o = 44 + 4 * nparts
        pts = struct.unpack(f"<{2 * npts}d", body[o:o + 16 * npts])
        xy = np.asarray(pts, dtype=float).reshape(-1, 2)
        for k in range(nparts):
            end = parts[k + 1] if k + 1 < nparts else npts
            rings.append(xy[parts[k]:end])
    return rings


def read_geojson(path):
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    rings = []
    for f in gj.get("features", [gj]):
        g = f.get("geometry", f)
        if g["type"] == "Polygon":
            rings += [np.asarray(r, dtype=float) for r in g["coordinates"]]
        elif g["type"] == "MultiPolygon":
            for poly in g["coordinates"]:
                rings += [np.asarray(r, dtype=float) for r in poly]
    return rings


def load_basin(path):
    path = Path(path)
    rings = (read_shapefile(path) if path.suffix.lower() == ".shp"
             else read_geojson(path))
    if not rings:
        raise ValueError(f"{path} : aucun polygone")
    allpts = np.vstack(rings)
    if np.abs(allpts[:, 0]).max() > 180 or np.abs(allpts[:, 1]).max() > 90:
        raise ValueError(f"{path} : coordonnees hors degres, reprojetez "
                         "l'emprise en WGS84 (EPSG:4326) avant de l'utiliser")
    print(f"  emprise : {len(rings)} anneau(x), {len(allpts)} sommets, "
          f"lon {allpts[:,0].min():.2f}..{allpts[:,0].max():.2f}, "
          f"lat {allpts[:,1].min():.2f}..{allpts[:,1].max():.2f}")
    return rings


def inside(rings, lon, lat):
    """Masque du bassin sur une grille, par lancer de rayon.

    Vectorise sur la grille et boucle sur les segments : un contour de
    quinze mille sommets sur une grille continentale ne passe pas par
    une double boucle en Python.
    """
    LON, LAT = np.meshgrid(lon, lat)
    inside_ = np.zeros(LON.shape, dtype=bool)
    for ring in rings:
        x, y = ring[:, 0], ring[:, 1]
        if x[0] != x[-1] or y[0] != y[-1]:
            x, y = np.r_[x, x[0]], np.r_[y, y[0]]
        for i in range(len(x) - 1):
            x1, y1, x2, y2 = x[i], y[i], x[i + 1], y[i + 1]
            if y1 == y2:
                continue
            straddle = (y1 > LAT) != (y2 > LAT)
            if not straddle.any():
                continue
            xint = x1 + (LAT - y1) * (x2 - x1) / (y2 - y1)
            inside_ ^= straddle & (LON < xint)
    return inside_


# ── Telechargement ──────────────────────────────────────────

def fetch(url, dest, timeout=120):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest


def exists(url, timeout=30):
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError):
        return False


def choose_layout(year=2024):
    """La disposition la moins couteuse que le seau offre reellement.

    Elles ne sont pas verifiables depuis un environnement sans acces :
    le script sonde plutot que de supposer, et dit ce qu'il a trouve.
    """
    for name, pattern in LAYOUTS:
        url = pattern.format(y=year, m=6, d=15)
        if exists(url):
            print(f"  disposition retenue : {name}")
            return name, pattern
    raise RuntimeError(
        "aucune disposition SILO n'a repondu. Verifiez l'acces reseau, "
        "puis la structure du seau sur longpaddock.qld.gov.au/silo/gridded-data")


# ── Lecture d'une grille ────────────────────────────────────

def read_grid(path):
    """Grille et coordonnees, GeoTIFF ou NetCDF."""
    if path.suffix.lower() in (".tif", ".tiff"):
        import rasterio
        with rasterio.open(path) as src:
            z = src.read(1, masked=True).filled(np.nan).astype("float32")
            t = src.transform
            lon = t.c + t.a * (np.arange(src.width) + 0.5)
            lat = t.f + t.e * (np.arange(src.height) + 0.5)
            nod = src.nodata
        if nod is not None:
            z = np.where(z == nod, np.nan, z)
        return lon, lat, z
    from netCDF4 import Dataset
    with Dataset(path) as ds:
        lon = np.asarray(ds.variables["lon"][:], dtype=float)
        lat = np.asarray(ds.variables["lat"][:], dtype=float)
        var = next(v for v in ("daily_rain", "monthly_rain", "rain")
                   if v in ds.variables)
        z = np.ma.filled(ds.variables[var][:], np.nan).astype("float32")
    return lon, lat, z


# ── Moyennes de bassin, par mois ────────────────────────────

def month_mean(year, month, rings, layout, pattern, cache=CACHE, keep=False):
    """Pluie moyenne sur le bassin pour un mois, en mm.

    Mise en cache : un demi-siecle de grilles continentales ne se
    retelecharge pas pour un simple changement de saisons.
    """
    cache.mkdir(parents=True, exist_ok=True)
    tag = cache / f"{year}{month:02d}.json"
    if tag.exists():
        return json.loads(tag.read_text())["mm"]

    tmp = cache / "tmp"
    total = None
    if layout == "monthly":
        f = fetch(pattern.format(y=year, m=month, d=1),
                  tmp / f"{year}{month:02d}.tif")
        lon, lat, z = read_grid(f)
        total = z
    elif layout == "annual":
        f = tmp / f"{year}.nc"
        if not f.exists():
            fetch(pattern.format(y=year, m=1, d=1), f)
        lon, lat, z = read_grid(f)
        import calendar
        start = sum(calendar.monthrange(year, m)[1] for m in range(1, month))
        n = calendar.monthrange(year, month)[1]
        total = np.nansum(z[start:start + n], axis=0)
    else:
        import calendar
        n = calendar.monthrange(year, month)[1]
        acc = None
        for d in range(1, n + 1):
            f = fetch(pattern.format(y=year, m=month, d=d),
                      tmp / f"{year}{month:02d}{d:02d}.tif")
            lon, lat, z = read_grid(f)
            acc = z if acc is None else acc + np.nan_to_num(z)
            if not keep:
                f.unlink(missing_ok=True)
        total = acc

    key = cache / "mask.npz"
    if key.exists():
        m = np.load(key)
        mask, w = m["mask"], m["w"]
    else:
        mask = inside(rings, lon, lat)
        # Ponderation par l'aire : une maille en degres retrecit vers le
        # sud, et le bassin couvre quatorze degres de latitude.
        w = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, len(lon)))
        np.savez_compressed(key, mask=mask, w=w)
        print(f"  masque du bassin : {int(mask.sum())} mailles")

    sel = mask & np.isfinite(total)
    mm = float(np.sum(total[sel] * w[sel]) / np.sum(w[sel])) if sel.any() \
        else float("nan")
    tag.write_text(json.dumps({"mm": mm}))
    if layout == "annual" and month == 12 and not keep:
        (tmp / f"{year}.nc").unlink(missing_ok=True)
    return mm


# ── Assemblage saisonnier ───────────────────────────────────

def parse_seasons(text):
    if not text:
        return dict(SEASONS)
    out = {}
    for part in text.split(","):
        name, span = part.split("=")
        a, b = (int(v) for v in span.split("-"))
        months = []
        m = a
        while True:
            months.append(m)
            if m == b:
                break
            m = 1 if m == 12 else m + 1
        out[name.strip()] = tuple(months)
    return out


def run(basin, first=1972, last=2025, seasons=None, cache=CACHE, quiet=False):
    """Totaux saisonniers par annee. Rend {saison: {annee: mm}}."""
    rings = load_basin(basin)
    seasons = parse_seasons(seasons) if isinstance(seasons, str) \
        else (seasons or dict(SEASONS))
    layout, pattern = choose_layout(min(last, 2024))

    table = {name: {} for name in seasons}
    for name, months in seasons.items():
        wraps = months[0] > months[-1]
        for year in range(first, last + 1):
            vals = []
            for m in months:
                # Une saison a cheval sur le changement d'annee est
                # rattachee a l'annee de son premier mois.
                y = year + 1 if (wraps and m < months[0]) else year
                if y > last + 1:
                    vals = []
                    break
                try:
                    vals.append(month_mean(y, m, rings, layout, pattern, cache))
                except Exception as e:
                    if not quiet:
                        print(f"    {y}-{m:02d} : {type(e).__name__}, ignore")
            if vals and all(v == v for v in vals):
                table[name][year] = float(sum(vals))
            if not quiet and year % 10 == 0:
                print(f"    {name} {year} : "
                      f"{table[name].get(year, float('nan')):.0f} mm")
    return table


def to_csv(table, path):
    years = sorted(set().union(*(t.keys() for t in table.values())))
    names = list(table)
    lines = ["year," + ",".join(names)]
    for y in years:
        lines.append(f"{y}," + ",".join(
            f"{table[n].get(y, ''):.1f}" if y in table[n] else ""
            for n in names))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--basin", required=True, help="emprise .shp ou .geojson")
    ap.add_argument("--from", dest="first", type=int, default=1972)
    ap.add_argument("--to", dest="last", type=int, default=2025)
    ap.add_argument("--seasons", default=None,
                    help='par exemple "warm=10-3,cool=4-9"')
    ap.add_argument("--csv", default="basin-rainfall.csv")
    a = ap.parse_args(argv)

    table = run(a.basin, a.first, a.last, a.seasons)
    print(f"\n{to_csv(table, a.csv)} ecrit")
    for name, series in table.items():
        if series:
            v = np.array(list(series.values()))
            print(f"  {name:6} {len(series)} annees, moyenne {v.mean():.0f} mm, "
                  f"ecart-type {v.std():.0f} mm, "
                  f"min {v.min():.0f}, max {v.max():.0f}")


if __name__ == "__main__":
    main()
