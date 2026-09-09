#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la courbe hypsometrique (pipeline/hypsometry.py).

Cette courbe sert de controle INDEPENDANT des surfaces SWOT : il faut
donc qu'elle soit elle-meme juste. La verification se fait sur une
cuvette conique, dont surface et volume ont une expression analytique.

Execution :  python tests/test_hypsometry.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import hypsometry as hy  # noqa: E402

# ── Aire des mailles ─────────────────────────────────────────

n = 300
step = 40000.0 / (n - 1)
xv, yv = np.meshgrid(np.linspace(0, 40000, n), np.linspace(0, 40000, n))
areas = hy.cell_areas(xv, yv)
assert abs(areas.mean() / step ** 2 - 1) < 0.01, areas.mean()

# Grille tournée : l'aire ne doit pas changer
ang = np.deg2rad(25.0)
rx = xv * np.cos(ang) - yv * np.sin(ang)
ry = xv * np.sin(ang) + yv * np.cos(ang)
assert abs(hy.cell_areas(rx, ry).mean() / areas.mean() - 1) < 0.01

# Grille étirée d'un facteur 2 en x : l'aire doit doubler
assert abs(hy.cell_areas(2 * xv, yv).mean() / areas.mean() - 2) < 0.01

# ── Cuvette conique : surface et volume analytiques ──────────
# Fond : z = -15 + r/2000, donc le contour z = h est un cercle de
# rayon r = 2000 (h + 15).

r = np.hypot(xv - 20000, yv - 20000)
bed = -15.0 + r / 2000.0
rows = hy.curve(bed, areas, np.arange(-15.0, -9.0, 0.5))

for h in (-14.0, -13.0, -12.0, -11.0):
    radius = (h + 15.0) * 2000.0
    exact_area = np.pi * radius ** 2 / 1e6
    got = hy.area_at(rows, h)
    assert abs(got - exact_area) / exact_area < 0.03, (h, got, exact_area)

    # Volume d'un cone : pi r^2 h / 3
    exact_vol = np.pi * radius ** 2 * (h + 15.0) / 3 / 1e9
    vol = next(t["volume_km3"] for t in rows if abs(t["level_m"] - h) < 1e-6)
    assert abs(vol - exact_vol) / exact_vol < 0.03, (h, vol, exact_vol)

# La courbe doit être monotone : plus haut, plus vaste
levels = [t["level_m"] for t in rows]
values = [t["area_km2"] for t in rows]
assert levels == sorted(levels)
assert all(b >= a for a, b in zip(values, values[1:])), values

# Sous le point bas, aucune surface
assert hy.area_at(rows, -15.0) < 1.0

# ── Reconstitution du fond depuis une sortie WAVE ────────────
# fond = niveau du scenario - profondeur simulee
wlvl = -11.0
depth = np.where(bed < wlvl, wlvl - bed, 0.0)
recovered = np.where(depth > 0, wlvl - depth, np.nan)
ok = np.isfinite(recovered)
assert np.allclose(recovered[ok], bed[ok], atol=1e-9)

# Les mailles hors d'eau à ce niveau restent indéterminées
assert not np.isfinite(recovered[bed >= wlvl]).any()

print("OK — aires de mailles invariantes par rotation, surfaces et volumes "
      "conformes à la géométrie exacte, reconstitution du fond validée.")
