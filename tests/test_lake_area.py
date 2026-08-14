#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du calcul de surface en eau (pipeline/lake_area.py).

La methode suit Rai et al. (2026). Les controles portent sur ce qui
peut fausser une serie de surfaces sans le moindre symptome :
  - bornes de fraction d'eau ;
  - filtre median : suppression du speckle sans erosion des rives ;
  - contrainte d'emprise remplacant le masque optique ;
  - sommation des scenes d'un meme passage et detection des passages
    partiels, qui se liraient sinon comme un assechement ;
  - propagation d'incertitude en somme quadratique.

Execution :  python tests/test_lake_area.py
"""

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import lake_area as la  # noqa: E402

CELL = 100.0 * 100.0          # maille de 100 m -> 10 000 m2

# ── Bornes de fraction d'eau ─────────────────────────────────

frac = np.array([[0.0, 0.05, 0.5], [0.95, 1.0, np.nan]])
mask = la.water_mask(frac, frac_range=(0.1, 0.99), median_size=0)
assert mask.tolist() == [[False, False, True], [True, False, False]], mask
# 1.0 est ecarte : une maille saturee traduit souvent une detection
# degradee plutot qu'une eau franche.
assert not mask[1, 1]

# Drapeau qualite
qual = np.array([[0, 3, 0], [1, 0, 0]])
mask_q = la.water_mask(np.full((2, 3), 0.5), qual, max_qual=1, median_size=0)
assert mask_q.tolist() == [[True, False, True], [True, True, True]]

# ── Filtre médian ────────────────────────────────────────────

# Un pixel isolé au milieu d'une zone sèche doit disparaître
speckle = np.zeros((9, 9), dtype=bool)
speckle[4, 4] = True
assert la.median_filter_mask(speckle, 5).sum() == 0, "speckle non supprimé"

# Un bloc d'eau franche doit survivre, sans être trop érodé
block = np.zeros((11, 11), dtype=bool)
block[3:8, 3:8] = True
kept = la.median_filter_mask(block, 5)
assert kept.sum() >= 9, f"bloc trop érodé : {kept.sum()} mailles"
assert kept[5, 5], "le cœur du bloc doit être conservé"

# Sans filtre, le speckle subsiste : le test précédent teste bien l'effet
assert la.median_filter_mask(speckle, 0).sum() == 1

# ── Surface ──────────────────────────────────────────────────

water_frac = np.full((10, 10), 0.8)
water_area = np.full((10, 10), CELL * 0.8)
res = la.area_from_arrays(water_area, water_frac, median_size=0)
assert res["n_cells"] == 100
assert abs(res["area_m2"] - 100 * CELL * 0.8) < 1e-6
assert res["uncert_m2"] is None

# Reconstitution à partir de la fraction quand water_area manque
res2 = la.area_from_arrays(None, water_frac, cell_area=CELL, median_size=0)
assert abs(res2["area_m2"] - res["area_m2"]) < 1e-6

# Somme quadratique des incertitudes
unc = np.full((10, 10), 30.0)
res3 = la.area_from_arrays(water_area, water_frac, uncert=unc, median_size=0)
assert abs(res3["uncert_m2"] - 30.0 * 10) < 1e-6, res3["uncert_m2"]

# Les mailles sèches ne contribuent pas
mixed_frac = np.where(np.indices((10, 10))[0] < 5, 0.8, 0.0)
mixed_area = mixed_frac * CELL
res4 = la.area_from_arrays(mixed_area, mixed_frac, median_size=0)
assert res4["n_cells"] == 50
assert abs(res4["area_m2"] - 50 * CELL * 0.8) < 1e-6

# ── Contrainte d'emprise ─────────────────────────────────────

# Emprise : un carré de 0,2° autour du lac
blon, blat = np.meshgrid(np.linspace(137.0, 137.2, 25),
                         np.linspace(-29.0, -28.8, 25))
boundary = np.column_stack([blon.ravel(), blat.ravel()])

# Granule couvrant largement au-delà
glon, glat = np.meshgrid(np.linspace(136.6, 137.6, 40),
                         np.linspace(-29.4, -28.4, 40))
inside = la.inside_boundary(glon, glat, boundary, tol_km=2.0)
assert inside.shape == glon.shape
# Seules les mailles proches du carré sont retenues
assert inside.sum() < glon.size / 2, inside.sum()
assert inside[np.argmin(np.abs(glat[:, 0] + 28.9)),
              np.argmin(np.abs(glon[0] - 137.1))], "le centre doit être inclus"
assert not inside[0, 0], "un coin éloigné doit être exclu"

# Sans emprise, aucune restriction
assert la.inside_boundary(glon, glat, None) is None

# La surface calculée dans l'emprise est inférieure à celle du granule
full = la.area_from_arrays(np.full(glon.shape, CELL),
                           np.full(glon.shape, 0.9), median_size=0)
clipped = la.area_from_arrays(np.full(glon.shape, CELL),
                              np.full(glon.shape, 0.9), inside=inside,
                              median_size=0)
assert clipped["area_m2"] < full["area_m2"]
assert clipped["n_cells"] == int(inside.sum())

# ── Assemblage des scènes ────────────────────────────────────

scenes = [
    {"area_m2": 400e6, "uncert_m2": 3e6, "n_cells": 40000, "covered_cells": 300},
    {"area_m2": 510e6, "uncert_m2": 4e6, "n_cells": 51000, "covered_cells": 320},
]
combo = la.combine_scenes(scenes, boundary_cells=625, min_coverage=0.15)
assert abs(combo["area_km2"] - 910.0) < 1e-6, combo
# Somme quadratique : sqrt(3^2 + 4^2) = 5
assert abs(combo["uncert_km2"] - 5.0) < 1e-6, combo
assert combo["n_scenes"] == 2
assert combo["partial"] is False

# Passage partiel : signalé plutôt que lu comme un assèchement
thin = [{"area_m2": 50e6, "uncert_m2": None, "n_cells": 5000,
         "covered_cells": 40}]
partial = la.combine_scenes(thin, boundary_cells=625, min_coverage=0.15)
assert partial["partial"] is True, partial
assert partial["uncert_km2"] is None
assert abs(partial["coverage"] - 40 / 625) < 1e-6

# Sans emprise connue, aucune couverture ne peut être jugée
unknown = la.combine_scenes(thin, boundary_cells=None)
assert unknown["coverage"] is None and unknown["partial"] is False

# ── Propagation d'incertitude (Eq. 10) ───────────────────────

# Les erreurs relatives se combinent en somme quadratique
assert abs(la.relative_volume_error(0.023, 0.151)
           - math.sqrt(0.023 ** 2 + 0.151 ** 2)) < 1e-12
# Ordres de grandeur de l'article : ~15 % puis ~23 %
low = la.relative_volume_error(0.023, 0.151)
high = la.relative_volume_error(0.1788, 0.151)
assert 0.14 < low < 0.16, low
assert 0.22 < high < 0.24, high
assert high > low

# ── Date extraite du nom de granule ──────────────────────────

name = ("SWOT_L2_HR_Raster_100m_UTM53J_N_x_x_x_020_394_102F_"
        "20260725T170200_20260725T170210_PID0_01.nc")
when = la.granule_datetime(name)
assert when is not None and when.strftime("%Y-%m-%d") == "2026-07-25", when
assert la.granule_datetime("readme.txt") is None

print("OK — filtres de fraction et de qualité, filtre médian, contrainte "
      "d'emprise, sommation des scènes, détection des passages partiels et "
      "propagation d'incertitude validés.")

# ══════════════════════════════════════════════════════════════
# Hygiene du repertoire de granules.
#
# Le dossier de telechargement contient des fichiers systeme macOS et,
# le cas echeant, des granules d'autres regions. Les premiers cassent
# la lecture, les seconds gonfleraient la surface s'ils n'etaient pas
# ecartes par l'emprise.
# ══════════════════════════════════════════════════════════════

import tempfile  # noqa: E402
import os  # noqa: E402

sys.path.insert(0, str(ROOT / "pipeline"))
from update_swot import list_nc_files  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "sub").mkdir()
    (root / "__MACOSX").mkdir()
    names = {
        "SWOT_L2_HR_Raster_100m_UTM53J_a.nc": True,
        "sub/SWOT_L2_HR_Raster_100m_UTM53J_b.nc": True,
        "._SWOT_L2_HR_Raster_100m_UTM53J_a.nc": False,   # AppleDouble
        "sub/._SWOT_L2_HR_Raster_100m_UTM53J_b.nc": False,
        ".hidden_100m.nc": False,
        "__MACOSX/SWOT_L2_HR_Raster_100m_c.nc": False,
        "SWOT_L2_HR_Raster_250m_d.nc": False,            # autre résolution
        "notes.txt": False,
    }
    for name in names:
        (root / name).write_bytes(b"x")

    found = {os.path.relpath(f, root) for f in list_nc_files(str(root), "100")}
    expected = {n for n, keep in names.items() if keep}
    assert found == expected, f"attendu {expected}, obtenu {found}"

    # Sans filtre de résolution, les 250 m entrent mais pas les parasites
    all_nc = {os.path.basename(f) for f in list_nc_files(str(root))}
    assert "SWOT_L2_HR_Raster_250m_d.nc" in all_nc
    assert not any(n.startswith("._") for n in all_nc)

print("OK — fichiers AppleDouble, dossiers cachés et __MACOSX écartés du "
      "listage des granules.")
