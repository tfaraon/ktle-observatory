#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extraction des grilles de pluie SILO sur le bassin, en GeoTIFF.

    python tools/rain_maps.py --basin Bassin.shp
    python tools/rain_maps.py --basin Bassin.shp --period 1972-2025 --period 2025
    python tools/rain_maps.py --basin Bassin.shp --season warm

Depuis l'interpreteur :

    >>> import rain_maps as rm
    >>> rm.BASIN = "/chemin/Bassin.shp"
    >>> rm.run()

Un GeoTIFF par periode demandee, en mm par an moyennes sur la periode.
Pour une periode d'un an c'est donc le total de cette annee. Rien n'est
calcule au-dela : la mise en page, les rampes de couleurs et les
comparaisons se font dans QGIS.

Chaque fichier declare EPSG:4326 et une valeur « sans donnee », avec un
fichier de calage et un .prj a cote par precaution. L'exterieur du
bassin est vide, donc QGIS le laisse transparent.

Les grilles decoupees sur l'emprise sont gardees dans data/rain_grids,
une archive par annee : changer de periode ou de saison ensuite ne
retelecharge rien. Le premier passage se reprend ou il s'est arrete.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basin_rainfall as br          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRIDS = ROOT / "data" / "rain_grids"

# ── Reglages ────────────────────────────────────────────────

BASIN = ""                          # .shp ou .geojson en WGS84
PERIODS = [(1972, 2025), (2025, 2025)]
SEASON = ""                         # "", "warm" (oct-mars), "cool" (avr-sept)
CLIP = True                         # vider hors du bassin
MIN_COVER = 0.9                     # part de mois exiges par maille
PAD = 0.25                          # marge autour de l'emprise, en degres
OUT = ""                            # dossier de sortie ; vide = ./rain_maps

NODATA = -9999.0


# ── Ecriture GeoTIFF ────────────────────────────────────────
#
# Ecrit a la main plutot qu'avec rasterio, pour que l'outil ne depende
# d'aucune bibliotheque geospatiale. Les trois etiquettes qui comptent
# sont l'echelle des pixels, le point d'accrochage, et le repertoire de
# cles geographiques sans lequel QGIS reclame un systeme de coordonnees
# a l'ouverture.

WGS84_WKT = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",'
             '6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
             'UNIT["Degree",0.0174532925199433]]')


def write_tif(path, grid, west, north, step, nodata=None):
    # Les constantes du module se lisent a l'appel et non comme valeur
    # par defaut : sinon elles seraient figees a l'import, et un reglage
    # pose depuis l'interpreteur resterait sans effet.
    nodata = NODATA if nodata is None else nodata
    from PIL import Image, TiffImagePlugin, TiffTags

    z = np.where(np.isfinite(grid), grid, nodata).astype("float32")
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[33550] = (float(step), float(step), 0.0)          # ModelPixelScale
    ifd.tagtype[33550] = TiffTags.DOUBLE
    # Le point d'accrochage vise le coin du pixel, non son centre
    ifd[33922] = (0.0, 0.0, 0.0, float(west), float(north), 0.0)
    ifd.tagtype[33922] = TiffTags.DOUBLE
    ifd[34735] = (1, 1, 0, 3,            # version, revision, 3 cles
                  1024, 0, 1, 2,         # modele : geographique
                  1025, 0, 1, 1,         # le pixel couvre une aire
                  2048, 0, 1, 4326)      # WGS 84
    ifd.tagtype[34735] = TiffTags.SHORT
    ifd[42113] = str(nodata)             # GDAL_NODATA
    ifd.tagtype[42113] = TiffTags.ASCII
    Image.fromarray(z, "F").save(path, tiffinfo=ifd)
    sidecars(Path(path), west, north, step)
    return path


def sidecars(path, west, north, step):
    """Calage et .prj a cote du GeoTIFF, par precaution.

    Les etiquettes internes suffisent normalement ; elles n'ont pas pu
    etre validees avec GDAL faute de l'avoir sous la main. Si jamais les
    cles geographiques etaient refusees, QGIS se rabat sur ces deux
    fichiers au lieu de reclamer un systeme de coordonnees.
    """
    # Un fichier de calage vise le centre du premier pixel, non son coin
    path.with_suffix(".tfw").write_text(
        f"{step:.10f}\n0.0\n0.0\n{-step:.10f}\n"
        f"{west + step / 2:.10f}\n{north - step / 2:.10f}\n", encoding="utf-8")
    path.with_suffix(".prj").write_text(WGS84_WKT, encoding="utf-8")


# ── Cache des grilles decoupees ─────────────────────────────

def window(rings, pad=None):
    """Emprise de travail, en degres, avec une marge."""
    pad = PAD if pad is None else pad
    pts = np.vstack(rings)
    return (pts[:, 0].min() - pad, pts[:, 0].max() + pad,
            pts[:, 1].min() - pad, pts[:, 1].max() + pad)


def read_any(path):
    """Grille et coordonnees, avec repli si rasterio manque."""
    try:
        return br.read_grid(path)
    except ImportError:
        sys.path.insert(0, str(ROOT / "pipeline"))
        from fetch_rainfall import read_geotiff
        z, lon, lat = read_geotiff(path)
        return lon, lat, z


def crop(lon, lat, z, box):
    w, e, s, n = box
    ix = np.where((lon >= w) & (lon <= e))[0]
    iy = np.where((lat >= s) & (lat <= n))[0]
    if not len(ix) or not len(iy):
        raise ValueError("l'emprise ne rencontre pas la grille SILO")
    return lon[ix], lat[iy], z[np.ix_(iy, ix)]


def cache_year(year, box, layout, pattern, quiet=False):
    """Les douze mois d'une annee, decoupes, dans une archive.

    L'archive porte les bornes du decoupage : si l'emprise change, les
    annees deja en cache ne s'empilent plus avec les nouvelles, et il
    vaut mieux s'en apercevoir ici qu'en regardant une carte fausse.
    """
    GRIDS.mkdir(parents=True, exist_ok=True)
    p = GRIDS / f"{year}.npz"
    if p.exists():
        d = np.load(p)
        if np.allclose(d["box"], box):
            return d["z"], d["lon"], d["lat"]
        if not quiet:
            print(f"  {year} : emprise differente en cache, recalcul")
    stack, lon, lat = [], None, None
    # La disposition annuelle sert les douze mois dans un seul fichier :
    # le telecharger douze fois serait douze fois trop long.
    whole_year = layout == "annual"
    fetched = None
    for m in range(1, 13):
        url = pattern.format(y=year, m=m, d=15)
        # Le nom vient de l'URL : c'est son extension qui dit au lecteur
        # s'il a affaire a un GeoTIFF ou a du NetCDF.
        dest = br.CACHE / Path(url).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if whole_year:
                if fetched is None:
                    br.fetch(url, dest)
                    fetched = read_any(dest)
                glon, glat, gz = fetched
            else:
                br.fetch(url, dest)
                glon, glat, gz = read_any(dest)
            if gz.ndim == 3:                    # 12 couches dans un fichier
                gz = gz[m - 1]
            clon, clat, cz = crop(glon, glat, gz, box)
            stack.append(cz.astype("float32"))
            lon, lat = clon, clat
        except Exception as e:
            if not quiet:
                print(f"  {year}-{m:02d} : {type(e).__name__}, mois ignore")
            stack.append(None)
        finally:
            if not whole_year:
                dest.unlink(missing_ok=True)
    if whole_year:
        (br.CACHE / Path(pattern.format(y=year, m=1, d=15)).name).unlink(missing_ok=True)
    shape = next((s.shape for s in stack if s is not None), None)
    if shape is None:
        raise RuntimeError(f"{year} : aucun mois lisible")
    z = np.stack([s if s is not None else np.full(shape, np.nan, "float32")
                  for s in stack])
    np.savez_compressed(p, z=z, lon=lon, lat=lat, box=np.asarray(box))
    return z, lon, lat


# ── Accumulation ────────────────────────────────────────────

def months_of(season):
    """Les mois d'une saison, et de quelle annee les prendre.

    La saison chaude va d'octobre a mars : ses trois derniers mois sont
    dans l'annee suivante, d'ou le decalage.
    """
    if season == "warm":
        return [(0, m) for m in (10, 11, 12)] + [(1, m) for m in (1, 2, 3)]
    if season == "cool":
        return [(0, m) for m in range(4, 10)]
    return [(0, m) for m in range(1, 13)]


def period_mean(first, last, box, layout, pattern, season="", cache=None,
                quiet=False):
    """Pluie moyenne par an sur une periode, maille par maille."""
    cache = {} if cache is None else cache
    total = count = lon = lat = None
    for y in range(first, last + 1):
        for shift, m in months_of(season):
            yy = y + shift
            if yy not in cache:
                try:
                    cache[yy] = cache_year(yy, box, layout, pattern, quiet)
                except Exception as e:
                    if not quiet:
                        print(f"  {yy} : {type(e).__name__}, annee ignoree")
                    cache[yy] = None
            if cache[yy] is None:
                continue
            z, glon, glat = cache[yy]
            g = z[m - 1]
            if total is None:
                total = np.zeros(g.shape, "float64")
                count = np.zeros(g.shape, "int32")
                lon, lat = glon, glat
            ok = np.isfinite(g)
            total[ok] += g[ok]
            count[ok] += 1
        if not quiet:
            print(f"  {y} ... ", end="", flush=True)
    if not quiet:
        print()
    if total is None:
        raise RuntimeError(f"{first}-{last} : aucune grille lue")
    nyears = last - first + 1
    wanted = len(months_of(season)) * nyears
    # Une maille trop trouee sort vide : comptee a zero elle rendrait la
    # carte plus seche la ou il manque des mois, sans rien signaler.
    mean = np.where(count >= wanted * MIN_COVER, total / nyears, np.nan)
    return mean.astype("float32"), lon, lat


# ── Passage complet ─────────────────────────────────────────

def parse_period(text):
    """« 1972-2025 » ou « 2025 »."""
    bits = str(text).split("-")
    if len(bits) == 1:
        return int(bits[0]), int(bits[0])
    if len(bits) == 2:
        return int(bits[0]), int(bits[1])
    raise ValueError(f"periode illisible : {text}")


def run(basin=None, periods=None, season=None, out=None, clip=None, quiet=False):
    basin = basin or BASIN
    if not basin:
        raise ValueError("indiquez l'emprise : rm.BASIN = '/chemin/Bassin.shp'")
    periods = [parse_period(p) if isinstance(p, str) else p
               for p in (PERIODS if periods is None else periods)]
    season = SEASON if season is None else season
    clip = CLIP if clip is None else clip
    outdir = Path(out or OUT or (Path.cwd() / "rain_maps"))
    outdir.mkdir(parents=True, exist_ok=True)
    if season and season not in ("warm", "cool"):
        raise ValueError("season : '', 'warm' ou 'cool'")

    rings = br.load_basin(basin)
    box = window(rings)
    last = max(p[1] for p in periods)
    layout, pattern = br.choose_layout(year=min(last, 2024))

    cache, mask, written = {}, None, []
    tag = f"_{season}" if season else ""
    for first, lastp in periods:
        if not quiet:
            print(f"{first}-{lastp}" + (f", saison {season}" if season else ""))
        grid, lon, lat = period_mean(first, lastp, box, layout, pattern,
                                     season, cache, quiet)
        if clip:
            if mask is None:
                mask = br.inside(rings, lon, lat)
            grid = np.where(mask, grid, np.nan)
        step = float(abs(lon[1] - lon[0]))
        name = (f"rain_{first}{tag}.tif" if first == lastp
                else f"rain_{first}-{lastp}{tag}.tif")
        p = write_tif(outdir / name, grid, float(lon.min() - step / 2),
                      float(lat.max() + step / 2), step)
        written.append(p)
        if not quiet:
            v = grid[np.isfinite(grid)]
            print(f"  {name:28} "
                  + (f"{v.min():7.1f} a {v.max():7.1f} mm/an" if v.size else "vide"))
    if not quiet:
        print(f"\n{len(written)} raster(s) dans {outdir}")
    return written


def preview(path):
    """Verification rapide d'un GeoTIFF : taille, bornes, valeurs."""
    lon, lat, z = read_any(Path(path))
    z = np.where(z <= NODATA + 1, np.nan, z)
    v = z[np.isfinite(z)]
    print(f"{Path(path).name} : {z.shape[1]}x{z.shape[0]} mailles, "
          f"lon {lon.min():.2f}..{lon.max():.2f}, "
          f"lat {lat.min():.2f}..{lat.max():.2f}")
    print(f"  valeurs : {v.min():.1f} a {v.max():.1f}, "
          f"mediane {np.median(v):.1f}, {100 * v.size / z.size:.0f} % remplies")
    return z


def main(argv=None):
    ap = argparse.ArgumentParser(description="Grilles de pluie SILO en GeoTIFF")
    ap.add_argument("--basin", default=BASIN, help=".shp ou .geojson en WGS84")
    ap.add_argument("--period", action="append", metavar="1972-2025",
                    help="repetable ; defaut : 1972-2025 et 2025")
    ap.add_argument("--season", default=SEASON, choices=["", "warm", "cool"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--no-clip", action="store_true",
                    help="garder le rectangle entier")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    run(basin=a.basin, periods=a.period, season=a.season, out=a.out,
        clip=not a.no_clip, quiet=a.quiet)


if __name__ == "__main__":
    main() if len(sys.argv) > 1 else run()
