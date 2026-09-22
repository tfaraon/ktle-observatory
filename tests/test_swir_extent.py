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

# ══════════════════════════════════════════════════════════════
# Appariement temporel et fenetre locale.
# ══════════════════════════════════════════════════════════════

# Sentinel-2 et SWOT passent rarement le même jour : une tolérance est
# indispensable, faute de quoi aucune image ne serait jamais appariée.
lv = {"2026-08-14": -13.04, "2026-08-15": -12.85, "2026-09-04": -12.95}
same = sw.nearest_level("2026-08-15", lv, 3)
assert same[0] == "2026-08-15" and same[2] == 0
near = sw.nearest_level("2026-08-17", lv, 3)
assert near[0] == "2026-08-15" and near[2] == 2
assert sw.nearest_level("2026-08-19", lv, 3) is None, "au-delà de 3 jours"
# À 5 jours de tolérance, le 15 (4 j) l'emporte sur le 14 (5 j)
assert sw.nearest_level("2026-08-19", lv, 5)[0] == "2026-08-15"
# À égalité d'écart, la passe retenue doit rester déterministe
assert sw.nearest_level("2026-08-16", {"2026-08-14": 1.0, "2026-08-18": 2.0},
                        3) is not None

# Fenêtre locale : la connexité ne s'y juge pas. Deux plans d'eau reliés
# HORS du cadre y paraissent disjoints ; avec la connexité, le calage
# écarterait l'un des deux et se tromperait de niveau.
m = 200
wx, wy = np.meshgrid(np.linspace(0, 20000, m), np.linspace(0, 20000, m))
# Deux sillons au même niveau, séparés par une flèche émergée au centre
bed_w = -13.0 + 0.6 * np.cos(wx / 20000 * 2 * np.pi) ** 2
obs_w = bed_w <= -12.7
ok_w = np.ones_like(obs_w, dtype=bool)
lv_w = np.arange(-13.5, -12.0, 0.05)

h_free, s_free, _ = sw.best_level(bed_w, obs_w, ok_w, lv_w, connected=False)
h_conn, s_conn, _ = sw.best_level(bed_w, obs_w, ok_w, lv_w, connected=True)
assert abs(h_free - (-12.7)) <= 0.06, h_free
assert s_free > s_conn, (
    "dans une fenêtre locale, la connexité dégrade le calage")

print("OK — appariement image/passe dans la tolérance, et calage sans "
      "connexité sur une fenêtre locale.")
