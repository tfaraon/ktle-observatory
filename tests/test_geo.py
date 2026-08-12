#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la conversion MGA/UTM -> WGS84 (pipeline/geo.py).

Une erreur de reprojection deplacerait le lac de plusieurs degres sans
message d'erreur : ces controles sont la premiere ligne de defense.

Execution :  python tests/test_geo.py
"""

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import geo  # noqa: E402

# ── Fuseau ───────────────────────────────────────────────────
assert geo.infer_zone(137.56) == 53, "Kati Thanda est en MGA53"
assert geo.infer_zone(-0.5) == 30 and geo.infer_zone(0.5) == 31
assert geo.zone_central_meridian(53) == 135.0

# ── Point de reference : Belt Bay ────────────────────────────
# Coordonnees du site d'extraction SWOT (config.yaml)
lon_bb, lat_bb = 137.56, -28.893
x, y = geo.lonlat_to_utm(lon_bb, lat_bb, 53)
assert 600000 < x < 900000 and 6700000 < y < 7000000, (x, y)
lon2, lat2 = geo.utm_to_lonlat(x, y, 53)
assert abs(lon2 - lon_bb) < 1e-7 and abs(lat2 - lat_bb) < 1e-7

# ── Aller-retour sur l'emprise reelle du modele ──────────────
worst = 0.0
for cx in (673229, 735000, 797654):
    for cy in (6778805, 6850000, 6924813):
        lon, lat = geo.utm_to_lonlat(cx, cy, 53)
        assert 136 < lon < 139 and -30 < lat < -27, (lon, lat)
        bx, by = geo.lonlat_to_utm(lon, lat, 53)
        worst = max(worst, math.hypot(bx - cx, by - cy))
assert worst < 0.001, f"aller-retour a {worst * 1000:.2f} mm"

# ── Version vectorisee identique a la version scalaire ───────
lon = np.array([[136.8, 137.5], [138.0, 137.0]])
lat = np.array([[-29.0, -28.5], [-28.0, -29.1]])
ex, ny_ = geo.lonlat_to_utm_array(lon, lat, 53)
for i in range(2):
    for j in range(2):
        sx, sy = geo.lonlat_to_utm(lon[i, j], lat[i, j], 53)
        assert abs(ex[i, j] - sx) < 1e-6 and abs(ny_[i, j] - sy) < 1e-6

# ── Convergence des meridiens ────────────────────────────────
# Nulle sur le meridien central, negative a l'est dans l'hemisphere sud
assert abs(geo.grid_convergence(135.0, -28.9, 53)) < 1e-9
east = geo.grid_convergence(138.0, -28.9, 53)
west = geo.grid_convergence(133.0, -28.9, 53)
assert east < 0 < west, (east, west)
assert 0.5 < abs(east) < 2.5, f"convergence inattendue : {east}"

# ── Hemisphere nord ──────────────────────────────────────────
lonn, latn = 5.0, 45.0
xn, yn = geo.lonlat_to_utm(lonn, latn, geo.infer_zone(lonn), south=False)
b_lon, b_lat = geo.utm_to_lonlat(xn, yn, geo.infer_zone(lonn), south=False)
assert abs(b_lon - lonn) < 1e-7 and abs(b_lat - latn) < 1e-7

# ── Detection du fuseau ──────────────────────────────────────
zone, err = geo.detect_zone(745000, 6800000, 137.56, -28.893)
assert zone == 53 and err < 0.2, (zone, err)

# Un indice incoherent doit etre rejete plutot que produire un lac
# deplace de plusieurs degres
bad_zone, bad_err = geo.detect_zone(745000, 6800000, 100.0, -28.9)
assert bad_zone is None and bad_err > 1.0, (bad_zone, bad_err)

# Un fuseau voisin est accepte s'il colle mieux
zone2, _ = geo.detect_zone(*geo.lonlat_to_utm(140.5, -28.9, 54),
                           140.5, -28.9)
assert zone2 == 54, zone2

print("OK — reprojection MGA53 <-> WGS84 : aller-retour submillimétrique, "
      "convergence des méridiens, détection et rejet de fuseau validés.")
