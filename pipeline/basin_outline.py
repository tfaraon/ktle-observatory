#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contour du bassin du lac Eyre, commun a la pluie et aux stations.

Par defaut, un contour SIMPLIFIE d'une trentaine de sommets, trace a la
main a partir des cartes du bassin : il suffit a choisir les stations
de jaugeage et a calculer une pluie moyenne, mais ses bords sont
approximatifs a quelques dizaines de kilometres pres, et le site le dit.

Pour le remplacer par le contour officiel (Geofabric du Bureau of
Meteorology, division de drainage « Lake Eyre Basin »), exporter ce
dernier en GeoJSON et indiquer son chemin dans config.yaml :

    catchment:
      boundary_geojson: data/leb_boundary.geojson
"""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# (longitude, latitude), sens horaire depuis l'ouest du Territoire du Nord
COARSE_OUTLINE = [
    (132.3, -23.2), (133.5, -22.4), (135.0, -21.3), (136.8, -20.2),
    (138.0, -19.3), (139.5, -20.0), (140.5, -20.5), (142.0, -20.9),
    (144.0, -20.6), (145.3, -21.0), (146.0, -22.5), (146.2, -24.2),
    (145.7, -25.8), (144.5, -26.3), (143.2, -27.0), (142.0, -28.2),
    (141.2, -29.5), (140.2, -30.8), (139.2, -31.5), (138.2, -31.3),
    (137.3, -30.8), (136.3, -30.2), (135.0, -29.6), (133.8, -28.6),
    (132.8, -27.2), (132.2, -25.5),
]


def load_outline(cfg=None):
    """Contour a utiliser : GeoJSON officiel s'il est configure, sinon simplifie.

    Renvoie (liste de (lon, lat), "official" ou "coarse").
    """
    path = ((cfg or {}).get("catchment") or {}).get("boundary_geojson")
    if path:
        p = Path(path)
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            gj = json.loads(p.read_text(encoding="utf-8"))
            rings = []
            feats = gj.get("features", [gj])
            for f in feats:
                g = f.get("geometry", f)
                if g.get("type") == "Polygon":
                    rings.append(g["coordinates"][0])
                elif g.get("type") == "MultiPolygon":
                    rings.extend(poly[0] for poly in g["coordinates"])
            if rings:
                ring = max(rings, key=len)
                return [(float(x), float(y)) for x, y in ring], "official"
    return list(COARSE_OUTLINE), "coarse"


def bbox(outline, pad=0.0):
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def contains(outline, lon, lat):
    """Point dans le polygone (lancer de rayon)."""
    inside = False
    n = len(outline)
    for i in range(n):
        x1, y1 = outline[i]
        x2, y2 = outline[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def grid_mask(outline, lons, lats):
    """Masque booleen (len(lats), len(lons)) des centres de mailles dans le bassin."""
    X, Y = np.meshgrid(np.asarray(lons, float), np.asarray(lats, float))
    inside = np.zeros(X.shape, dtype=bool)
    n = len(outline)
    for i in range(n):
        x1, y1 = outline[i]
        x2, y2 = outline[(i + 1) % n]
        if y1 == y2:
            continue
        crosses = (y1 > Y) != (y2 > Y)
        x_cross = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= crosses & (X < x_cross)
    return inside
