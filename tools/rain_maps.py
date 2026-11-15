#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cartes de pluie sur le bassin, pretes pour QGIS.

Depuis l'interpreteur :

    >>> import rain_maps as rm
    >>> rm.BASIN = "/chemin/Bassin.shp"
    >>> rm.run()

Depuis le terminal :

    python tools/rain_maps.py --basin Bassin.shp
    python tools/rain_maps.py --basin Bassin.shp --season warm

Ce que basin_rainfall.py fait n'est pas ce qu'il faut ici : il reduit
chaque grille a une moyenne sur le bassin et jette la grille. Une carte
demande les champs eux-memes, donc ce script accumule les grilles
mensuelles SILO maille par maille et ecrit des GeoTIFF.

Il en sort quatre, pour une figure a deux ou trois panneaux :

    rain_mean_1972-2025.tif    moyenne annuelle de la periode, en mm/an
    rain_2025.tif              total de l'annee cartographiee, en mm
    rain_anomaly_2025.tif      ecart a la moyenne, en mm
    rain_ratio_2025.tif        part de la normale, en %

Les deux derniers ne sont pas demandes mais c'est presque toujours eux
qu'on finit par montrer : une carte de 2025 seule se lit mal sans
savoir ce qu'une annee ordinaire donne au meme endroit.

Chaque GeoTIFF declare EPSG:4326 et une valeur « sans donnee », donc
QGIS les ouvre sans rien demander et laisse l'exterieur du bassin
transparent. Deux fichiers de style .qml sont ecrits a cote : chargez-les
par Proprietes > Symbologie > Style > Charger un style.

Cout et cache. Une periode de 54 ans fait 648 grilles mensuelles. Elles
sont decoupees sur l'emprise du bassin et gardees dans
data/rain_grids/, une archive par annee, environ 2 Mo : changer de
periode ou de saison ensuite ne retelecharge rien. Le premier passage
prend le temps qu'il prend, et se reprend ou il s'est arrete.
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basin_rainfall as br          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRIDS = ROOT / "data" / "rain_grids"

# ── Reglages ────────────────────────────────────────────────

BASIN = ""              # .shp ou .geojson en WGS84 ; vide = demande
FIRST, LAST = 1972, 2025        # periode de reference
YEAR = 2025                     # annee a cartographier
SEASON = ""                     # "", "warm" (oct-mars) ou "cool" (avr-sept)
CLIP = True                     # masquer hors du bassin
MIN_COVER = 0.9                 # part de mois exiges par maille
PAD = 0.25                      # marge autour de l'emprise, en degres
OUT = ""                        # dossier de sortie ; vide = ./rain_maps

NODATA = -9999.0


# ── Ecriture GeoTIFF ────────────────────────────────────────
#
# Ecrit a la main plutot qu'avec rasterio : le reste de l'outil ne
# depend d'aucune bibliotheque geospatiale, et il serait dommage qu'une
# carte echoue sur une installation manquante. Les trois etiquettes qui
# comptent sont l'echelle des pixels, le point d'accrochage, et le
# repertoire de cles geographiques sans lequel QGIS reclame un systeme
# de coordonnees a l'ouverture.

def write_tif(path, grid, west, north, step, nodata=None):
    # Les constantes du module se lisent a l'appel et non comme valeur
    # par defaut : sinon elles seraient figees a l'import, et un
    # reglage pose depuis l'interpreteur resterait sans effet.
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


WGS84_WKT = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",'
             '6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
             'UNIT["Degree",0.0174532925199433]]')


def sidecars(path, west, north, step):
    """Fichier de calage et .prj a cote du GeoTIFF.

    Les etiquettes internes suffisent normalement. Ces deux fichiers
    sont une precaution : ils sont ecrits a la main, n'ont pas pu etre
    valides ici faute de GDAL, et si jamais les cles geographiques
    etaient refusees, QGIS se rabat sur eux au lieu de reclamer un
    systeme de coordonnees.
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


def year_path(year, season=""):
    return GRIDS / f"{year}{'-' + season if season else ''}.npz"


def cache_year(year, rings, box, layout, pattern, quiet=False):
    """Les douze mois d'une annee, decoupes, dans une archive.

    L'archive porte les bornes du decoupage : si l'emprise change, les
    annees deja en cache ne s'empilent plus avec les nouvelles, et il
    vaut mieux s'en apercevoir ici qu'en regardant une carte fausse.
    """
    GRIDS.mkdir(parents=True, exist_ok=True)
    p = year_path(year)
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
    if season == "warm":
        return [(0, m) for m in (10, 11, 12)] + [(1, m) for m in (1, 2, 3)]
    if season == "cool":
        return [(0, m) for m in range(4, 10)]
    return [(0, m) for m in range(1, 13)]


def period_total(years, rings, box, layout, pattern, season="", quiet=False):
    """Somme par maille et nombre de mois valides, sur une liste d'annees.

    La saison chaude mord sur l'annee suivante : l'annee Y a besoin des
    grilles de Y et de Y+1, d'ou le decalage porte par months_of.
    """
    total = count = lon = lat = None
    cache = {}

    def grids(y):
        if y not in cache:
            cache[y] = cache_year(y, rings, box, layout, pattern, quiet)
        return cache[y]

    for y in years:
        for shift, m in months_of(season):
            try:
                z, glon, glat = grids(y + shift)
            except Exception as e:
                if not quiet:
                    print(f"  {y + shift} : {type(e).__name__}, annee ignoree")
                continue
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
        raise RuntimeError("aucune grille lue")
    return total, count, lon, lat


def enough(total, count, wanted, min_cover=None):
    """Somme par maille, ou « sans donnee » si trop de mois manquent."""
    min_cover = MIN_COVER if min_cover is None else min_cover
    out = np.where(count >= wanted * min_cover, total, np.nan)
    return out.astype("float32")


# ── Passage complet ─────────────────────────────────────────

def run(basin=None, first=None, last=None, year=None, season=None,
        out=None, clip=None, quiet=False):
    basin = basin or BASIN
    if not basin:
        raise ValueError("indiquez l'emprise : rm.BASIN = '/chemin/Bassin.shp'")
    first = FIRST if first is None else first
    last = LAST if last is None else last
    year = YEAR if year is None else year
    season = SEASON if season is None else season
    clip = CLIP if clip is None else clip
    outdir = Path(out or OUT or (Path.cwd() / "rain_maps"))
    outdir.mkdir(parents=True, exist_ok=True)
    if season and season not in ("warm", "cool"):
        raise ValueError("season : '', 'warm' ou 'cool'")
    if not first <= year <= last:
        print(f"  note : {year} est hors de {first}-{last}, l'ecart a la "
              "moyenne compare donc a une periode qui ne la contient pas")

    rings = br.load_basin(basin)
    box = window(rings)
    layout, pattern = br.choose_layout(year=min(last, 2024))
    per_year = len(months_of(season))

    if not quiet:
        print(f"periode {first}-{last}" + (f", saison {season}" if season else "")
              + f" : {last - first + 1} annees")
    ptotal, pcount, lon, lat = period_total(range(first, last + 1), rings, box,
                                            layout, pattern, season, quiet)
    if not quiet:
        print(f"annee {year}")
    ytotal, ycount, _, _ = period_total([year], rings, box, layout, pattern,
                                        season, quiet)

    nyears = last - first + 1
    mean = enough(ptotal, pcount, per_year * nyears) / nyears
    single = enough(ytotal, ycount, per_year)

    mask = br.inside(rings, lon, lat) if clip else None
    if mask is not None:
        mean = np.where(mask, mean, np.nan)
        single = np.where(mask, single, np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        anomaly = (single - mean).astype("float32")
        ratio = np.where(mean > 0, single / mean * 100.0, np.nan).astype("float32")

    step = float(abs(lon[1] - lon[0]))
    west = float(lon.min() - step / 2)
    north = float(lat.max() + step / 2)
    tag = f"_{season}" if season else ""
    files = {
        f"rain_mean_{first}-{last}{tag}.tif": (mean, "mm/an, moyenne"),
        f"rain_{year}{tag}.tif": (single, f"mm, {year}"),
        f"rain_anomaly_{year}{tag}.tif": (anomaly, "mm, ecart a la moyenne"),
        f"rain_ratio_{year}{tag}.tif": (ratio, "% de la normale"),
    }
    written = []
    for name, (grid, what) in files.items():
        p = write_tif(outdir / name, grid, west, north, step)
        written.append(p)
        if not quiet:
            v = grid[np.isfinite(grid)]
            print(f"  {name:34} {what:26} "
                  + (f"{v.min():7.1f} a {v.max():7.1f}" if v.size else "vide"))
    written += write_styles(outdir, mean, anomaly)
    if not quiet:
        print(f"\n{len(written)} fichiers dans {outdir}")
        print("QGIS : glissez les .tif, puis Proprietes > Symbologie > "
              "Style > Charger un style pour le .qml du meme nom.")
    return written


# ── Styles QGIS ─────────────────────────────────────────────
#
# Une rampe par defaut en gris ne montre rien d'une carte de pluie. Deux
# styles suffisent : une rampe sequentielle pour les totaux, une rampe
# divergente centree sur zero pour l'ecart, sans quoi l'oeil place le
# milieu de l'echelle n'importe ou.

QML = """<!DOCTYPE qgis>
<qgis version="3.34" styleCategories="Symbology">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1"
                    classificationMin="{lo}" classificationMax="{hi}">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0">
{items}
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
  </pipe>
</qgis>
"""

SEQUENTIAL = ["#fff7ec", "#fee8c8", "#fdd49e", "#fdbb84", "#fc8d59",
              "#4eb3d3", "#2b8cbe", "#0868ac", "#084081"]
DIVERGING = ["#8c510a", "#bf812d", "#dfc27d", "#f6e8c3", "#f5f5f5",
             "#c7eae5", "#80cdc1", "#35978f", "#01665e"]


def write_styles(outdir, mean, anomaly):
    def ramp(path, lo, hi, colours):
        n = len(colours) - 1
        items = "\n".join(
            f'          <item value="{lo + (hi - lo) * i / n:.3f}" '
            f'color="{c}" alpha="255" label="{lo + (hi - lo) * i / n:.0f}"/>'
            for i, c in enumerate(colours))
        path.write_text(QML.format(lo=f"{lo:.3f}", hi=f"{hi:.3f}", items=items),
                        encoding="utf-8")
        return path

    out = []
    v = mean[np.isfinite(mean)]
    if v.size:
        out.append(ramp(outdir / "style_totals.qml", 0.0,
                        float(np.percentile(v, 99)), SEQUENTIAL))
    a = anomaly[np.isfinite(anomaly)]
    if a.size:
        # Symetrique autour de zero : sans cela le blanc du milieu se
        # pose sur une valeur quelconque et la carte ment
        m = float(np.percentile(np.abs(a), 98)) or 1.0
        out.append(ramp(outdir / "style_anomaly.qml", -m, m, DIVERGING))
    return out


def preview(path):
    """Verification rapide d'un GeoTIFF ecrit : taille, bornes, valeurs."""
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
    ap = argparse.ArgumentParser(description="Cartes de pluie pour QGIS")
    ap.add_argument("--basin", default=BASIN, help=".shp ou .geojson en WGS84")
    ap.add_argument("--first", type=int, default=FIRST)
    ap.add_argument("--last", type=int, default=LAST)
    ap.add_argument("--year", type=int, default=YEAR)
    ap.add_argument("--season", default=SEASON, choices=["", "warm", "cool"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--no-clip", action="store_true",
                    help="garder le rectangle entier")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    run(basin=a.basin, first=a.first, last=a.last, year=a.year,
        season=a.season, out=a.out, clip=not a.no_clip, quiet=a.quiet)


if __name__ == "__main__":
    main() if len(sys.argv) > 1 else run()
