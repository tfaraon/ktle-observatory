#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du calage SWIR (pipeline/swir_extent.py).

Le rivage observe par SWIR se trouve, par definition, au niveau reel de
l'eau. Chercher le niveau qui le reproduit au mieux, puis le comparer a
la WSE SWOT du jour, donne une estimation empirique du decalage entre
les deux referentiels verticaux — c'est le point que ni la grille de
geoide ni l'article ne permettaient de trancher avec ces donnees.

Ces controles verifient que le calage retrouve un decalage connu, qu'il
resiste au bruit d'observation, et qu'il signale les situations ou le
niveau est mal contraint.

Execution :  python tests/test_swir_extent.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import swir_extent as sw  # noqa: E402

# ── Indice de Jaccard ────────────────────────────────────────

a = np.array([[True, True], [False, False]])
b = np.array([[True, False], [True, False]])
assert abs(sw.jaccard(a, a) - 1.0) < 1e-9
assert abs(sw.jaccard(a, b) - 1 / 3) < 1e-9
assert sw.jaccard(np.zeros((2, 2), bool), np.zeros((2, 2), bool)) is None

# Le masque de validité restreint la comparaison
valid = np.array([[True, True], [False, False]])
assert abs(sw.jaccard(a, b, valid) - 0.5) < 1e-9

# ── Calage sur une cuvette de géométrie connue ───────────────

n = 300
xv, yv = np.meshgrid(np.linspace(0, 40000, n), np.linspace(0, 40000, n))
bed = -15.0 + np.hypot(xv - 20000, yv - 20000) / 2000.0

TRUE_LEVEL = -12.60
SWOT_LEVEL = -13.00                      # décalage réel : +0.40 m
observed = bed <= TRUE_LEVEL
everywhere = np.ones_like(observed, dtype=bool)
levels = np.arange(SWOT_LEVEL - 1.5, SWOT_LEVEL + 1.5, 0.05)

h, score, curve = sw.best_level(bed, observed, everywhere, levels)
assert abs(h - TRUE_LEVEL) <= 0.06, h
assert score > 0.98, score
assert abs((h - SWOT_LEVEL) - 0.40) <= 0.06

# La courbe doit couvrir la plage demandée et culminer à l'optimum
assert len(curve) == len(levels)
assert max(t["jaccard"] for t in curve) == score

# ── Robustesse au bruit d'observation ────────────────────────

rng = np.random.default_rng(0)
for rate, tol in ((0.03, 0.15), (0.10, 0.30)):
    noisy = observed ^ (rng.random(observed.shape) < rate)
    h_n, s_n, _ = sw.best_level(bed, noisy, everywhere, levels)
    assert abs(h_n - TRUE_LEVEL) <= tol, (rate, h_n)
    assert s_n < score, "le bruit doit dégrader l'accord"

# ── Diagnostic de plateau ────────────────────────────────────
# Sur une rive en pente douce, plusieurs niveaux expliquent aussi bien
# le rivage : le calage est alors peu contraint, et doit le signaler.

gentle = -15.0 + np.hypot(xv - 20000, yv - 20000) / 20000.0
obs_gentle = gentle <= TRUE_LEVEL
h_g, _, curve_g = sw.best_level(gentle, obs_gentle, everywhere, levels)

steep_width = sw.sharpness(curve, h)
gentle_width = sw.sharpness(curve_g, h_g)
assert steep_width is not None and gentle_width is not None
assert gentle_width > steep_width, (steep_width, gentle_width)

assert sw.sharpness([], None) is None

# ── Date extraite du nom de masque ───────────────────────────

assert sw.mask_date("2026-08-19_S2_spit_swir_water_class.tif") == "2026-08-19"
assert sw.mask_date("S2_20260819_swir_water_class.tif") == "2026-08-19"
assert sw.mask_date("sans_date_water_class.tif") is None

print("OK — indice de Jaccard, calage d'un décalage connu, robustesse au "
      "bruit et détection d'un optimum mal contraint validés.")
