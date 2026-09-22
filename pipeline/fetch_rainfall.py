#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pluie sur le bassin du lac Eyre, d'apres les grilles quotidiennes SILO.

    python pipeline/fetch_rainfall.py
    python pipeline/fetch_rainfall.py --demo

SILO (gouvernement du Queensland) publie chaque jour une grille de pluie
sur l'Australie au pas de 0,05 degre, sous licence CC BY 4.0, hebergee
sur AWS. En GeoTIFF, un fichier ne contient qu'une journee : on ne
telecharge donc que les jours manquants, jamais les fichiers annuels
de 410 Mo.

Produits (data/rainfall.json, data/rain_maps/*.png) :
  - une image par jour sur la fenetre choisie (30 jours par defaut),
  - les cumuls sur 7 et 30 jours,
  - pour chaque jour, la pluie moyenne sur le bassin et le maximum.

Les images sont reprojetees en Mercator ligne par ligne, pour se poser
exactement sur la carte Leaflet ; en dehors du bassin elles sont
transparentes, comme sous 1 mm.

Precautions affichees sur le site : les grilles sont interpolees a
partir de pluviometres rares dans ce desert, et SILO peut reviser les
jours recents ; les derniers jours sont donc retelecharges a chaque
passage.
"""

import argparse
import json
import math
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

import basin_outline as bo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_FILE = DATA / "rainfall.json"
MAP_DIR = DATA / "rain_maps"
CACHE_DIR = DATA / "rain_cache"
SILO_URL = ("https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official/"
            "daily/daily_rain/{y}/{ymd}.daily_rain.tif")
USER_AGENT = "ktle-observatory/1.0 (research outreach; github.com/tfaraon/ktle-observatory)"

# Classes de pluie (mm) et couleurs, du plus sec au plus humide ; sous la
# premiere classe la maille reste transparente.
BREAKS = [1, 5, 10, 25, 50, 100, 200]
COLOURS = ["#C9E7F2", "#8CC8E0", "#4FA3CF", "#2A73B8", "#3F4FA8", "#6A3D9A", "#A0307E"]

DEFAULTS = {"days": 30, "revisit_days": 3, "pad_deg": 0.3, "image_width": 540}


def settings(cfg):
    s = dict(DEFAULTS, **((cfg or {}).get("rainfall") or {}))
    s["days"] = max(7, min(int(s["days"]), 90))
    s["revisit_days"] = max(0, min(int(s["revisit_days"]), 14))
    return s


# ── Lecture des GeoTIFF ─────────────────────────────────────────

def read_geotiff(path):
    """Grille (2D), longitudes et latitudes des centres de mailles.

    rasterio s'il est installe ; sinon Pillow, qui lit le georeferencement
    dans les balises GeoTIFF (echelle 33550, point d'attache 33922).
    """
    try:
        import rasterio
        with rasterio.open(path) as src:
            a = src.read(1).astype("float32")
            t = src.transform
            nodata = src.nodata
            lons = t.c + t.a * (np.arange(a.shape[1]) + 0.5)
            lats = t.f + t.e * (np.arange(a.shape[0]) + 0.5)
    except ImportError:
        im = Image.open(path)
        a = np.array(im, dtype="float32")   # copie : Pillow rend un tableau en lecture seule
        tags = im.tag_v2
        sx, sy = tags[33550][0], tags[33550][1]
        tie = tags[33922]
        x0, y0 = tie[3] - tie[0] * sx, tie[4] + tie[1] * sy
        lons = x0 + sx * (np.arange(a.shape[1]) + 0.5)
        lats = y0 - sy * (np.arange(a.shape[0]) + 0.5)
        nd = tags.get(42113)
        nodata = float(str(nd).strip("\x00 ")) if nd not in (None, "") else None
    if nodata is not None:
        a[a == nodata] = np.nan
    a[a < 0] = np.nan
    return a, np.asarray(lons, float), np.asarray(lats, float)


def crop(a, lons, lats, box):
    w, s, e, n = box
    ci = np.where((lons >= w) & (lons <= e))[0]
    ri = np.where((lats >= s) & (lats <= n))[0]
    return (a[ri.min():ri.max() + 1, ci.min():ci.max() + 1],
            lons[ci.min():ci.max() + 1], lats[ri.min():ri.max() + 1])


def download(url, dest, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        f.write(r.read())


# ── Rendu ──────────────────────────────────────────────────────

def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def colourise(grid, mask):
    """RGBA : classes de pluie, transparent hors bassin et sous 1 mm."""
    rgba = np.zeros(grid.shape + (4,), dtype=np.uint8)
    valid = mask & np.isfinite(grid)
    for k, lo in enumerate(BREAKS):
        hi = BREAKS[k + 1] if k + 1 < len(BREAKS) else np.inf
        sel = valid & (grid >= lo) & (grid < hi)
        rgba[sel, :3] = _hex(COLOURS[k])
        rgba[sel, 3] = 215
    return rgba


def mercator_rows(lats, height):
    """Indices de lignes de la grille a echantillonner pour une image
    dont les lignes sont regulierement espacees en Mercator (nord en haut).
    """
    def merc(phi):
        return math.log(math.tan(math.pi / 4 + math.radians(phi) / 2))
    step = abs(lats[1] - lats[0]) if len(lats) > 1 else 0.05
    top, bottom = max(lats) + step / 2, min(lats) - step / 2
    y_top, y_bot = merc(top), merc(bottom)
    out = []
    lat_desc = lats[0] > lats[-1]
    for r in range(height):
        y = y_top + (y_bot - y_top) * (r + 0.5) / height
        phi = math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)
        i = int(round((top - step / 2 - phi) / step)) if lat_desc else \
            int(round((phi - (bottom + step / 2)) / step))
        out.append(min(max(i, 0), len(lats) - 1))
    return out, (bottom, top)


def render_png(grid, lons, lats, mask, path, width):
    rgba = colourise(grid, mask)
    if lats[0] < lats[-1]:          # nord en haut
        rgba, lats_d = rgba[::-1], lats[::-1]
    else:
        lats_d = lats
    lon_span = lons[-1] - lons[0]
    # Hauteur proportionnelle en Mercator, pour une image non deformee
    def merc(phi):
        return math.log(math.tan(math.pi / 4 + math.radians(phi) / 2))
    h_ratio = (merc(max(lats)) - merc(min(lats))) / math.radians(lon_span or 1)
    height = max(2, int(round(width * h_ratio)))
    rows, _ = mercator_rows(lats_d, height)
    cols = np.clip(np.round(np.linspace(0, len(lons) - 1, width)).astype(int), 0, len(lons) - 1)
    Image.fromarray(rgba[np.ix_(rows, cols)], "RGBA").save(path, optimize=True)


def stats(grid, mask):
    v = grid[mask & np.isfinite(grid)]
    if v.size == 0:
        return None, None
    return round(float(v.mean()), 2), round(float(v.max()), 1)


# ── Mise a jour ────────────────────────────────────────────────

def load_day(d, s, box, fetch, force):
    """Grille du jour d, recadree sur le bassin : cache, sinon SILO."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{d:%Y%m%d}.npz"
    if cache.exists() and not force:
        z = np.load(cache)
        return z["rain"], z["lons"], z["lats"]
    tmp = CACHE_DIR / f"{d:%Y%m%d}.tif"
    fetch(SILO_URL.format(y=d.year, ymd=f"{d:%Y%m%d}"), tmp)
    a, lons, lats = read_geotiff(tmp)
    a, lons, lats = crop(a, lons, lats, box)
    np.savez_compressed(cache, rain=a.astype("float32"), lons=lons, lats=lats)
    tmp.unlink(missing_ok=True)
    return a, lons, lats


def update(cfg, demo=False, fetch=download, today=None, write=True):
    s = settings(cfg)
    outline, kind = bo.load_outline(cfg)
    box = bo.bbox(outline, pad=s["pad_deg"])
    today = today or datetime.now(timezone.utc).date()
    MAP_DIR.mkdir(parents=True, exist_ok=True)

    days, grids, errors = [], {}, []
    lons = lats = mask = None
    for k in range(1, s["days"] + 1):
        d = today - timedelta(days=k)
        try:
            if demo:
                g, lo, la = demo_grid(d, box)
            else:
                g, lo, la = load_day(d, s, box, fetch, force=k <= s["revisit_days"])
        except Exception as e:
            # Le jour le plus recent n'est souvent pas encore publie
            errors.append(f"{d}: {type(e).__name__}")
            continue
        if mask is None:
            lons, lats = lo, la
            mask = bo.grid_mask(outline, lons, lats)
        grids[d] = g
    if not grids:
        prev = load_previous(demo)
        if prev is None:
            raise SystemExit("SILO injoignable et aucun fichier précédent : " + "; ".join(errors[:3]))
        prev["stale"], prev["errors"] = True, errors[:10]
        payload = prev
    else:
        step = abs(lats[1] - lats[0]) if len(lats) > 1 else 0.05
        bounds = [[float(min(lats) - step / 2), float(min(lons) - step / 2)],
                  [float(max(lats) + step / 2), float(max(lons) + step / 2)]]
        keep = set()
        for d in sorted(grids, reverse=True):
            name = f"{d:%Y%m%d}.png"
            render_png(grids[d], lons, lats, mask, MAP_DIR / name, s["image_width"])
            keep.add(name)
            mean, mx = stats(grids[d], mask)
            days.append({"date": str(d), "mean_mm": mean, "max_mm": mx, "png": f"rain_maps/{name}"})
        totals = {}
        for label, n in (("sum7", 7), ("sum30", 30)):
            sel = [d for d in sorted(grids, reverse=True)[:n]]
            tot = np.nansum(np.stack([grids[d] for d in sel]), axis=0)
            name = f"{label}.png"
            render_png(tot, lons, lats, mask, MAP_DIR / name, s["image_width"])
            keep.add(name)
            mean, mx = stats(tot, mask)
            totals[label] = {"from": str(min(sel)), "to": str(max(sel)), "n_days": len(sel),
                             "mean_mm": mean, "max_mm": mx, "png": f"rain_maps/{name}"}
        for old in MAP_DIR.glob("*.png"):
            if old.name not in keep:
                old.unlink()
        payload = {
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "demo": bool(demo), "stale": False, "errors": errors[:10],
            "source": "SILO, Queensland Government", "licence": "CC BY 4.0",
            "source_url": "https://www.longpaddock.qld.gov.au/silo/",
            "outline": {"kind": kind, "coords": [[round(y, 3), round(x, 3)] for x, y in outline]},
            "bounds": bounds,
            "scale": {"breaks_mm": BREAKS, "colours": COLOURS},
            "days": days, **totals,
        }
    if write:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def load_previous(demo):
    if not OUT_FILE.exists():
        return None
    try:
        prev = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return prev if bool(prev.get("demo")) == bool(demo) else None


def demo_grid(d, box):
    """Champ synthetique : deux amas de pluie qui derivent, marque demonstration."""
    w, s, e, n = box
    lons = np.round(np.arange(w, e, 0.05), 3)
    lats = np.round(np.arange(n, s, -0.05), 3)
    X, Y = np.meshgrid(lons, lats)
    t = d.toordinal() % 30
    g = 40 * np.exp(-(((X - 143 + t * 0.05) ** 2) + (Y + 23) ** 2) / 2.0)
    g += 15 * np.exp(-(((X - 137) ** 2) + (Y + 27 + t * 0.03) ** 2) / 1.5)
    return g.astype("float32"), lons, lats


def main():
    ap = argparse.ArgumentParser(description="Pluie SILO sur le bassin du lac Eyre")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--demo", action="store_true", help="Données synthétiques, sans réseau")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    p = update(cfg, demo=args.demo)
    print(f"JSON écrit : {OUT_FILE}{' (démonstration)' if p.get('demo') else ''}")
    if p.get("sum7"):
        print(f"  7 jours : {p['sum7']['mean_mm']} mm en moyenne sur le bassin, "
              f"{p['sum7']['max_mm']} mm au plus")
        print(f"  30 jours : {p['sum30']['mean_mm']} mm en moyenne, {p['sum30']['max_mm']} mm au plus")
    print(f"  contour du bassin : {'officiel' if p['outline']['kind'] == 'official' else 'simplifié'}")
    if p.get("stale"):
        print("  SILO injoignable : dernier jeu valide conservé")


if __name__ == "__main__":
    main()
