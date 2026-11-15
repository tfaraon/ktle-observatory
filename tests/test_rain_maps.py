#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extraction des grilles de pluie (tools/rain_maps.py), sans reseau.

Ce qui peut se tromper ici est silencieux : un GeoTIFF sans systeme de
coordonnees s'ouvre quand meme et se pose a cote du bassin ; un
decalage d'un demi-pixel ne se voit qu'en superposant le contour ; une
moyenne qui compte les mois manquants comme zero donne une carte plus
seche partout, sans rien signaler.

Execution :  python tests/test_rain_maps.py
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import basin_rainfall as br          # noqa: E402
import rain_maps as rm               # noqa: E402

checks = []


def check(label, ok, detail=""):
    checks.append((label, bool(ok)))
    if not ok:
        print(f"ECHEC — {label}"
              + (f" : {detail}" if detail is not None and detail != "" else ""))


# Grille continentale de reference, au pas SILO
STEP = 0.05
LON = np.round(np.arange(129.0, 150.0, STEP) + STEP / 2, 5)
LAT = np.round(np.arange(-32.0, -17.0, STEP)[::-1] + STEP / 2, 5)

# Bassin d'essai : un carre franc, pour pouvoir verifier le masque
RING = np.array([[136.0, -26.0], [140.0, -26.0], [140.0, -22.0],
                 [136.0, -22.0], [136.0, -26.0]])

tmp = Path(tempfile.mkdtemp())
rm.GRIDS = tmp / "grids"
br.CACHE = tmp / "dl"

# Champ synthetique : 10 mm par mois partout, sauf 2025 deux fois plus
# arrose, pour que les moyennes aient une valeur connue d'avance.
served = []


def fake_fetch(url, dest, timeout=120):
    served.append(url)
    year = int(Path(url).name[:4])
    value = 20.0 if year == 2025 else 10.0
    grid = np.full((len(LAT), len(LON)), value, "float32")
    rm.write_tif(dest, grid, LON.min() - STEP / 2, LAT.max() + STEP / 2, STEP)


br.fetch = fake_fetch
br.choose_layout = lambda year=2024: ("monthly", "silo/{y}{m:02d}.tif")
br.load_basin = lambda path: [RING]


# ── Le GeoTIFF ecrit doit se relire tel quel ────────────────

f = tmp / "probe.tif"
probe = np.arange(6 * 8, dtype="float32").reshape(6, 8)
rm.write_tif(f, probe, 136.0, -22.0, STEP)
lon, lat, z = rm.read_any(f)
check("valeurs relues identiques", np.allclose(z, probe), z[0, :3])
# Le point d'accrochage vise le coin : le premier centre est a un demi-pixel
check("premier centre a un demi-pixel du coin",
      abs(lon[0] - (136.0 + STEP / 2)) < 1e-6, lon[0])
check("latitudes descendantes depuis le nord",
      abs(lat[0] - (-22.0 - STEP / 2)) < 1e-6 and lat[1] < lat[0], lat[:2])
check("pas de grille conserve", abs((lon[1] - lon[0]) - STEP) < 1e-9)

tags = Image.open(f).tag_v2
check("echelle des pixels declaree", 33550 in tags, sorted(tags)[:6])
check("point d'accrochage declare", 33922 in tags)
# Sans cette etiquette QGIS reclame un systeme de coordonnees a l'ouverture
check("EPSG:4326 declare dans les cles geographiques",
      34735 in tags and 4326 in tuple(tags[34735]), tags.get(34735))
check("modele geographique, pixel couvrant une aire",
      tuple(tags[34735])[4:8] == (1024, 0, 1, 2)
      and tuple(tags[34735])[8:12] == (1025, 0, 1, 1), tags.get(34735))
check("valeur sans donnee declaree",
      str(tags.get(42113)).strip() == str(rm.NODATA), tags.get(42113))

# Calage de secours, au cas ou les cles geographiques seraient refusees
tfw = [float(x) for x in (tmp / "probe.tfw").read_text().split()]
check("fichier de calage : pas de grille", abs(tfw[0] - STEP) < 1e-9, tfw[0])
check("fichier de calage : axe des latitudes vers le sud",
      abs(tfw[3] + STEP) < 1e-9, tfw[3])
# Il vise le centre du premier pixel, le GeoTIFF son coin : l'ecart est
# d'un demi-pixel, et s'y tromper decale la carte sur le terrain
check("fichier de calage : vise le centre du premier pixel",
      abs(tfw[4] - (136.0 + STEP / 2)) < 1e-9
      and abs(tfw[5] - (-22.0 - STEP / 2)) < 1e-9, tfw[4:])
check("fichier de calage d'accord avec le GeoTIFF",
      abs(tfw[4] - lon[0]) < 1e-9 and abs(tfw[5] - lat[0]) < 1e-9,
      (tfw[4:], lon[0], lat[0]))
check("projection ecrite a cote",
      "WGS_1984" in (tmp / "probe.prj").read_text())

# Les trous doivent sortir en « sans donnee », non en zero
holed = probe.copy()
holed[0, 0] = np.nan
rm.write_tif(tmp / "holed.tif", holed, 136.0, -22.0, STEP)
raw = np.asarray(Image.open(tmp / "holed.tif"))
check("les mailles vides prennent la valeur sans donnee",
      raw[0, 0] == rm.NODATA, raw[0, 0])


# ── Decoupage ───────────────────────────────────────────────

box = rm.window([RING])
check("marge appliquee autour de l'emprise",
      abs(box[0] - (136.0 - rm.PAD)) < 1e-9 and abs(box[3] - (-22.0 + rm.PAD)) < 1e-9,
      box)
clon, clat, cz = rm.crop(LON, LAT, np.zeros((len(LAT), len(LON)), "float32"), box)
check("decoupage reduit vraiment la grille",
      cz.shape[1] < len(LON) and cz.shape[0] < len(LAT), cz.shape)
check("le decoupage couvre tout le bassin",
      clon.min() <= 136.0 and clon.max() >= 140.0
      and clat.min() <= -26.0 and clat.max() >= -22.0,
      (clon.min(), clon.max(), clat.min(), clat.max()))


# ── Lecture des periodes ────────────────────────────────────

check("periode sur deux bornes", rm.parse_period("1972-2025") == (1972, 2025))
check("annee seule", rm.parse_period("2025") == (2025, 2025))
try:
    rm.parse_period("1972-2000-2025")
    check("periode illisible refusee", False)
except ValueError:
    check("periode illisible refusee", True)


# ── Passage complet ─────────────────────────────────────────

out = tmp / "maps"
files = rm.run(basin="essai.shp", periods=[(2020, 2025), (2025, 2025)],
               out=out, quiet=True)
names = [p.name for p in files]
check("un raster par periode demandee",
      names == ["rain_2020-2025.tif", "rain_2025.tif"], names)
check("rien d'autre n'est ecrit",
      not list(out.glob("*.qml")) and len(list(out.glob("*.tif"))) == 2,
      [p.name for p in out.iterdir()])


def grid_of(name):
    _, _, g = rm.read_any(out / name)
    return np.where(g <= rm.NODATA + 1, np.nan, g)


mean = grid_of("rain_2020-2025.tif")
single = grid_of("rain_2025.tif")
inside_cells = np.isfinite(mean)

# Cinq annees a 120 mm et une a 240 : la moyenne vaut 140
check("moyenne annuelle juste",
      np.allclose(mean[inside_cells], 140.0), np.nanmin(mean))
# Une periode d'un an rend le total de cette annee
check("periode d'un an : total de l'annee",
      np.allclose(single[inside_cells], 240.0), np.nanmin(single))

# ── Masque ──
lonm, latm, _ = rm.read_any(out / "rain_2025.tif")
LO, LA = np.meshgrid(lonm, latm)
outside = (LO < 136.0) | (LO > 140.0) | (LA < -26.0) | (LA > -22.0)
check("l'exterieur du bassin est vide", np.all(np.isnan(single[outside])),
      np.nansum(single[outside]))
check("l'interieur du bassin est rempli",
      np.all(np.isfinite(single[~outside])),
      np.isnan(single[~outside]).sum())
check("la marge est bien presente dans le raster", outside.any(), outside.sum())

# Sans masquage, tout le rectangle porte des valeurs
out2 = tmp / "maps_full"
rm.run(basin="essai.shp", periods=[(2024, 2025)], out=out2, clip=False,
       quiet=True)
_, _, full = rm.read_any(out2 / "rain_2024-2025.tif")
check("sans masquage le rectangle entier est rempli",
      np.all(full > rm.NODATA + 1), (full <= rm.NODATA + 1).sum())


# ── Cache ───────────────────────────────────────────────────

before = len(served)
rm.run(basin="essai.shp", periods=[(2020, 2025)], out=tmp / "again", quiet=True)
check("le cache evite tout retelechargement", len(served) == before,
      len(served) - before)

# Deux periodes qui se recouvrent ne doivent pas tout relire deux fois
before = len(served)
rm.run(basin="essai.shp", periods=[(2020, 2025), (2022, 2025), (2025, 2025)],
       out=tmp / "overlap", quiet=True)
check("des periodes qui se recouvrent se partagent les grilles",
      len(served) == before, len(served) - before)

# Une emprise differente ne doit pas s'empiler sur les annees en cache
rm.PAD = 1.0
before = len(served)
rm.run(basin="essai.shp", periods=[(2025, 2025)], out=tmp / "wide", quiet=True)
check("une emprise elargie force le recalcul", len(served) > before,
      len(served) - before)
rm.PAD = 0.25


# ── Mois manquants ──────────────────────────────────────────

# Une annee entiere absente doit vider les mailles, pas les sous-estimer
rm.GRIDS = tmp / "holes"
br.CACHE = tmp / "dl2"
missing = {2022}


def holey_fetch(url, dest, timeout=120):
    if int(Path(url).name[:4]) in missing:
        raise OSError("mois absent")
    fake_fetch(url, dest)


br.fetch = holey_fetch
outh = tmp / "holey"
rm.run(basin="essai.shp", periods=[(2020, 2025)], out=outh, quiet=True)
_, _, gh = rm.read_any(outh / "rain_2020-2025.tif")
gh = np.where(gh <= rm.NODATA + 1, np.nan, gh)
# Cinq annees sur six, soit 83 % des mois : sous le seuil de 90 %
check("une annee manquante vide les mailles plutot que de les sous-estimer",
      np.all(np.isnan(gh)), int(np.isfinite(gh).sum()))

rm.MIN_COVER = 0.8
rm.GRIDS = tmp / "holes2"
rm.run(basin="essai.shp", periods=[(2020, 2025)], out=tmp / "holey2", quiet=True)
_, _, g2 = rm.read_any(tmp / "holey2" / "rain_2020-2025.tif")
g2 = np.where(g2 <= rm.NODATA + 1, np.nan, g2)
v2 = g2[np.isfinite(g2)]
# 2020, 2021, 2023 et 2024 a 120 mm, 2025 a 240 : 720 mm sur la periode.
# La moyenne divise par les six annees demandees et non par les cinq
# lues, sinon l'annee manquante remonterait la moyenne au lieu de la
# laisser telle quelle.
check("un seuil abaisse laisse passer, en divisant par la periode entiere",
      bool(v2.size) and np.allclose(v2, 120.0),
      float(v2[0]) if v2.size else "vide")
rm.MIN_COVER = 0.9
br.fetch = fake_fetch


# ── Saisons ─────────────────────────────────────────────────

check("saison chaude : six mois a cheval sur deux annees",
      rm.months_of("warm") == [(0, 10), (0, 11), (0, 12), (1, 1), (1, 2), (1, 3)],
      rm.months_of("warm"))
check("saison fraiche dans l'annee",
      rm.months_of("cool") == [(0, m) for m in range(4, 10)])
check("sans saison, les douze mois", len(rm.months_of("")) == 12)

rm.GRIDS = tmp / "grids"
outs = tmp / "warm"
fw = rm.run(basin="essai.shp", periods=[(2024, 2024)], season="warm",
            out=outs, quiet=True)
check("le nom de fichier porte la saison",
      [p.name for p in fw] == ["rain_2024_warm.tif"], [p.name for p in fw])
_, _, g = rm.read_any(outs / "rain_2024_warm.tif")
g = np.where(g <= rm.NODATA + 1, np.nan, g)
# Oct-dec 2024 a 10 mm et jan-mars 2025 a 20 : 30 + 60 = 90
check("la saison chaude prend bien les mois de l'annee suivante",
      np.allclose(g[np.isfinite(g)], 90.0), np.nanmin(g))


# ── Garde-fous d'appel ──────────────────────────────────────

try:
    rm.run(basin="essai.shp", season="ete", quiet=True)
    check("une saison inconnue est refusee", False)
except ValueError:
    check("une saison inconnue est refusee", True)

rm.BASIN = ""
try:
    rm.run(quiet=True)
    check("sans emprise, message clair", False)
except ValueError as e:
    check("sans emprise, message clair", "BASIN" in str(e), str(e)[:60])


bad = [c for c, ok in checks if not ok]
if bad:
    print(f"\n{len(bad)}/{len(checks)} verifications en echec")
    sys.exit(1)
print(f"OK — {len(checks)} verifications : GeoTIFF georeference pour QGIS "
      "(EPSG:4326, accrochage au coin, sans-donnee, calage de secours), "
      "decoupage, moyennes justes, masque du bassin, cache partage entre "
      "periodes, mois manquants, saisons.")
