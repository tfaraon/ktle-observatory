#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pluie SILO sur le bassin (pipeline/fetch_rainfall.py), sans reseau.

Un vrai GeoTIFF georeference est fabrique, lu par le chemin Pillow (celui
d'une machine sans rasterio), recadre sur le bassin et rendu en image.
Ce qui est verifie : le georeferencement, le masque du bassin,
l'alignement des images en Mercator sur la carte, les moyennes et
cumuls, le cache (pas de retelechargement inutile) et la tolerance a un
jour pas encore publie.

Execution :  python tests/test_rainfall.py
"""

import math
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, TiffImagePlugin, TiffTags

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import basin_outline as bo      # noqa: E402
import fetch_rainfall as fr     # noqa: E402

# Grille de type SILO : 0,05 degre, nord en haut, origine au coin nord-ouest
LON0, LAT0, STEP = 131.0, -18.0, 0.05
NX, NY = int((148.0 - LON0) / STEP), int((LAT0 + 33.0) / STEP)
lons = LON0 + STEP * (np.arange(NX) + 0.5)
lats = LAT0 - STEP * (np.arange(NY) + 0.5)


def write_geotiff(path, grid):
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[33550] = (STEP, STEP, 0.0)
    ifd.tagtype[33550] = TiffTags.DOUBLE
    ifd[33922] = (0.0, 0.0, 0.0, LON0, LAT0, 0.0)
    ifd.tagtype[33922] = TiffTags.DOUBLE
    ifd[42113] = "-32767"
    ifd.tagtype[42113] = TiffTags.ASCII
    Image.fromarray(grid.astype("float32"), "F").save(path, tiffinfo=ifd)


# Pluie : bande de 20 mm autour de 25 S, 3 mm partout ailleurs, et une
# maille « sans donnee »
field = np.full((NY, NX), 3.0, dtype="float32")
band = np.abs(lats + 25.0) < 0.3
field[band, :] = 20.0
field[10, 10] = -32767

calls = []


def fake_fetch(url, dest):
    calls.append(url)
    if "20260921" in url:            # le jour le plus recent n'est pas encore publie
        raise OSError("404")
    write_geotiff(dest, field)


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    fr.OUT_FILE, fr.MAP_DIR, fr.CACHE_DIR = td / "rainfall.json", td / "maps", td / "cache"

    # ── Lecture du GeoTIFF sans rasterio ──
    write_geotiff(td / "t.tif", field)
    a, lo, la = fr.read_geotiff(td / "t.tif")
    assert a.shape == (NY, NX)
    assert abs(lo[0] - (LON0 + STEP / 2)) < 1e-9 and abs(la[0] - (LAT0 - STEP / 2)) < 1e-9
    assert np.isnan(a[10, 10]), "valeur sans donnée"

    # ── Masque du bassin ──
    outline, kind = bo.load_outline({})
    assert kind == "coarse"
    assert bo.contains(outline, 144.25, -23.44), "Longreach dans le bassin"
    assert bo.contains(outline, 141.11, -27.60), "Nappa Merrie dans le bassin"
    assert bo.contains(outline, 133.88, -23.70), "Alice Springs dans le bassin"
    assert not bo.contains(outline, 143.83, -27.99), "Thargomindah (Bulloo) hors du bassin"
    assert not bo.contains(outline, 146.9, -19.3), "Townsville hors du bassin"
    m = bo.grid_mask(outline, [144.25, 150.0], [-23.44])
    assert m.tolist() == [[True, False]]

    # ── Mise à jour : 30 jours, le plus récent manquant ──
    p = fr.update({"rainfall": {"days": 30, "revisit_days": 3}}, fetch=fake_fetch,
                  today=date(2026, 9, 22))
    assert len(p["days"]) == 29, len(p["days"])
    assert any("2026-09-21" in e for e in p["errors"])
    assert p["days"][0]["date"] == "2026-09-20"
    d0 = p["days"][0]
    assert 3.0 < d0["mean_mm"] < 20.0 and d0["max_mm"] == 20.0, d0
    assert p["sum7"]["n_days"] == 7 and p["sum7"]["max_mm"] == 140.0, p["sum7"]
    assert p["outline"]["kind"] == "coarse"
    assert len(list(fr.MAP_DIR.glob("*.png"))) == 29 + 2

    # ── Image : transparente hors bassin, colorée dedans, bien placée ──
    im = np.asarray(Image.open(fr.MAP_DIR / "20260920.png"))
    (s, w), (n, e) = p["bounds"]
    H, W = im.shape[:2]

    def pixel(lon, lat):
        merc = lambda phi: math.log(math.tan(math.pi / 4 + math.radians(phi) / 2))
        r = int((merc(n) - merc(lat)) / (merc(n) - merc(s)) * H)
        c = int((lon - w) / (e - w) * W)
        return im[min(r, H - 1), min(c, W - 1)]

    assert pixel(141.0, -25.0)[3] > 0, "pluie de 20 mm dans le bassin : colorée"
    assert tuple(pixel(141.0, -25.0)[:3]) == fr._hex(fr.COLOURS[2]), "classe 10 à 25 mm"
    assert tuple(pixel(141.0, -22.0)[:3]) == fr._hex(fr.COLOURS[0]), "classe 1 à 5 mm"
    assert pixel(146.3, -19.0)[3] == 0, "hors du bassin : transparent"
    # Alignement Mercator : la bande de 25 S tombe bien à 25 S sur la carte
    for lat in (-24.8, -25.2):
        assert tuple(pixel(141.0, lat)[:3]) == fr._hex(fr.COLOURS[2]), lat
    for lat in (-24.2, -25.8):
        assert tuple(pixel(141.0, lat)[:3]) == fr._hex(fr.COLOURS[0]), lat

    # ── Série longue : accumulée d'un passage à l'autre ──
    assert len(p["series"]) == 29 and p["series"][0][0] < p["series"][-1][0]
    p_next = fr.update({"rainfall": {"days": 30, "revisit_days": 3}}, fetch=fake_fetch,
                       today=date(2026, 10, 12))          # trois semaines plus tard
    dates = [d for d, _ in p_next["series"]]
    assert "2026-08-24" in dates and "2026-10-11" in dates, "anciennes valeurs gardées"
    assert len(dates) == len(set(dates)) and dates == sorted(dates)
    assert len(dates) > 30, len(dates)

    # ── Cache : seuls les jours récents sont retéléchargés ──
    calls.clear()
    fr.update({"rainfall": {"days": 30, "revisit_days": 3}}, fetch=fake_fetch,
              today=date(2026, 9, 22))
    assert len(calls) == 3, calls

    # ── Panne totale : dernier jeu gardé ──
    def dead(url, dest):
        raise OSError("réseau coupé")
    for f in fr.CACHE_DIR.glob("*.npz"):
        f.unlink()
    p2 = fr.update({}, fetch=dead, today=date(2026, 9, 22))
    assert p2["stale"] is True and p2["days"]

print("OK — GeoTIFF lu sans rasterio, masque du bassin, images alignées en Mercator, "
      "classes de pluie, moyennes et cumuls, cache, jour manquant et panne.")
