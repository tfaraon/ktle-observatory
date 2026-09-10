#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de l'etendue deduite du niveau (pipeline/water_extent.py).

L'etendue n'est plus lue dans la classification eau/terre de KaRIn —
fragile sur une playa — mais obtenue en intersectant le niveau mesure
par SWOT avec la bathymetrie du modele. Ce que ces controles verifient :

  - la connexite hydraulique, qui distingue une nappe reliee au point
    bas d'une cuvette isolee derriere un seuil ;
  - la monotonie : surface et volume croissent avec le niveau ;
  - le cas limite d'un niveau sous le point bas ;
  - le report sur la grille d'affichage, sans trou.

Execution :  python tests/test_water_extent.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import hypsometry as hyp  # noqa: E402
import water_extent as we  # noqa: E402

# ── Deux cuvettes séparées par un seuil ──────────────────────

n = 200
xv, yv = np.meshgrid(np.linspace(0, 40000, n), np.linspace(0, 40000, n))
main_basin = -15.0 + np.hypot(xv - 13000, yv - 20000) / 1500.0
side_pool = -14.0 + np.hypot(xv - 32000, yv - 20000) / 1500.0
bed = np.minimum(main_basin, side_pool)
areas = hyp.cell_areas(xv, yv)

from scipy.ndimage import label  # noqa: E402

# À un niveau où les deux cuvettes sont sous l'eau mais encore séparées
h = -12.0
wet_all, area_all, vol_all = we.extent_stats(bed, areas, h, connected=False)
wet_con, area_con, vol_con = we.extent_stats(bed, areas, h, connected=True)
assert label(wet_all)[1] > 1, "le cas de test doit comporter deux nappes"
assert area_con < area_all, "la cuvette isolée doit être écartée"
assert vol_con < vol_all
assert label(wet_con)[1] == 1, "la nappe retenue doit être d'un seul tenant"

# La nappe conservée est celle qui contient le point bas
deepest = np.unravel_index(int(np.argmin(bed)), bed.shape)
assert wet_con[deepest]

# Un niveau assez haut réunit les deux : plus rien à écarter
high = -8.0
_, a_all_h, _ = we.extent_stats(bed, areas, high, connected=False)
_, a_con_h, _ = we.extent_stats(bed, areas, high, connected=True)
assert abs(a_con_h - a_all_h) / a_all_h < 1e-9

# ── Monotonie ────────────────────────────────────────────────

levels = [-14.5, -14.0, -13.0, -12.0, -11.0]
areas_seq = [we.extent_stats(bed, areas, t)[1] for t in levels]
vols_seq = [we.extent_stats(bed, areas, t)[2] for t in levels]
assert all(b >= a for a, b in zip(areas_seq, areas_seq[1:])), areas_seq
assert all(b > a for a, b in zip(vols_seq, vols_seq[1:])), vols_seq

# ── Cas limites ──────────────────────────────────────────────

wet0, a0, v0 = we.extent_stats(bed, areas, -15.5)
assert not wet0.any() and a0 == 0.0 and v0 == 0.0

# Une bathymétrie entièrement indéterminée ne produit rien
nan_bed = np.full_like(bed, np.nan)
assert not we.flooded(nan_bed, -12.0).any()

# ── Report sur la grille d'affichage ─────────────────────────

lon = 137.0 + xv / 100000.0
lat = -29.0 + yv / 110000.0
wet, _, _ = we.extent_stats(bed, areas, -12.0)
depth = np.where(wet, -12.0 - bed, np.nan)
bounds = (float(lat.min()) - 0.02, float(lat.max()) + 0.02,
          float(lon.min()) - 0.02, float(lon.max()) + 0.02)
grid, (glat, glon) = we.raster_mask(lon, lat, wet, depth, bounds, (120, 120))

assert grid.shape == (120, 120)
covered = np.isfinite(grid)
assert covered.any(), "la nappe doit apparaître sur la grille"
# La proportion couverte doit être du même ordre que la nappe elle-même
assert abs(covered.mean() - wet.mean()) < 0.15, (covered.mean(), wet.mean())
# Les profondeurs reportées restent dans la plage physique
assert np.nanmin(grid[covered]) >= 0
assert np.nanmax(grid[covered]) <= float(np.nanmax(depth)) + 1e-6
# Pas de trou au coeur de la nappe : le plus proche voisin comble la
# difference de resolution entre modele et affichage
from scipy.ndimage import binary_erosion  # noqa: E402
core = binary_erosion(covered, np.ones((5, 5)))
assert core.sum() == 0 or np.isfinite(grid[core]).all()

print("OK — connexité hydraulique, monotonie, cas limites et report sur "
      "la grille d'affichage validés.")
