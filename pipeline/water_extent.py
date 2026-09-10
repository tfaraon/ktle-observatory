#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Etendue de la nappe d'eau pour un niveau donne.

SWOT mesure de facon fiable une grandeur : la HAUTEUR de la surface
libre. Sa classification eau/terre maille par maille, elle, est fragile
sur une playa — croute de sel humide et eau tres peu profonde renvoient
a KaRIn des retrodiffusions voisines (0-15 dB), d'ou le chatoiement, les
effets de recouvrement et la geometrie de fauchee visibles sur les
granules bruts.

Cette chaine part donc du niveau :

    etendue(t) = { mailles du modele dont le fond <= h(t) }

ou h(t) est la WSE SWOT au site de reference. Le contour obtenu est net,
continu, et hérite de la resolution de la bathymetrie plutot que du
bruit du radar.

Deux raffinements comptent :

  - CONNEXITE. Toutes les depressions sous h ne sont pas en eau : une
    cuvette isolee derriere un seuil reste seche. On ne retient que la
    composante hydrauliquement reliee au point bas, ce qui reproduit la
    fragmentation du lac en sous-bassins a mesure qu'il s'assèche.

  - REFERENTIEL. La bathymetrie du modele est en AHD, la WSE SWOT en
    EGM2008 : scenarios.wlvl_offset est ajoute au niveau avant
    l'intersection.

    python pipeline/water_extent.py
    python pipeline/water_extent.py --level -12.9
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import geo  # noqa: E402
import hypsometry as hyp  # noqa: E402
import scenario_field as sfield  # noqa: E402

OUT_FILE = ROOT / "data" / "water_extent.json"
MAP_DIR = ROOT / "data" / "extent_maps"


def flooded(bed, level, connected=True):
    """Mailles en eau au niveau demande.

    connected=True ne conserve que la nappe reliee au point bas : une
    depression isolee sous le meme niveau n'est pas remplie tant qu'un
    seuil l'en separe.
    """
    wet = np.isfinite(bed) & (bed <= level)
    if not connected or not wet.any():
        return wet

    from scipy.ndimage import label

    labels, n = label(wet)
    if n <= 1:
        return wet
    deep = np.where(np.isfinite(bed), bed, np.inf)
    seed = np.unravel_index(int(np.argmin(deep)), bed.shape)
    if not wet[seed]:
        return wet
    return labels == labels[seed]


def extent_stats(bed, areas, level, connected=True):
    """Surface et volume de la nappe, en m2 et m3."""
    wet = flooded(bed, level, connected)
    if not wet.any():
        return wet, 0.0, 0.0
    area = float(areas[wet].sum())
    volume = float((areas[wet] * (level - bed[wet])).sum())
    return wet, area, volume


def to_lonlat(xv, yv, zone, south=True):
    return geo.utm_to_lonlat_array(xv, yv, zone, south)


def raster_mask(lon, lat, wet, depth, bounds, shape):
    """Masque du modele reporte sur une grille lon/lat reguliere.

    La grille du modele (~500 m) est plus grossiere que la grille
    d'affichage : un simple comptage laisserait des trous, on affecte
    donc a chaque case la maille de modele la plus proche.
    """
    from scipy.spatial import cKDTree

    lat0, lat1, lon0, lon1 = bounds
    ny, nx = shape
    glat = np.linspace(lat0, lat1, ny)
    glon = np.linspace(lon0, lon1, nx)
    mlon, mlat = np.meshgrid(glon, glat)

    good = np.isfinite(lon) & np.isfinite(lat)
    kx = np.cos(np.radians((lat0 + lat1) / 2)) or 1.0
    tree = cKDTree(np.column_stack([lon[good].ravel() * kx,
                                    lat[good].ravel()]))
    dist, idx = tree.query(np.column_stack([mlon.ravel() * kx,
                                            mlat.ravel()]),
                           distance_upper_bound=0.02)   # ~2 km
    inside = np.isfinite(dist)

    wet_flat = wet[good].ravel()
    dep_flat = np.where(np.isfinite(depth), depth, 0.0)[good].ravel()
    safe = np.where(inside, idx, 0)

    out = np.full(mlon.shape, np.nan)
    taken = wet_flat[safe].reshape(mlon.shape) & inside.reshape(mlon.shape)
    out[taken] = dep_flat[safe].reshape(mlon.shape)[taken]
    return out, (glat, glon)


def write_png(depth_grid, path, vmax=None):
    """Profondeur -> PNG bleu, opacite croissante avec la profondeur."""
    from PIL import Image

    grid = depth_grid[::-1, :]
    finite = grid[np.isfinite(grid)]
    if not finite.size:
        return 0
    hi = float(vmax if vmax else max(np.percentile(finite, 98), 0.2))
    norm = np.clip(np.nan_to_num(grid) / hi, 0, 1)
    alpha = np.where(np.isfinite(grid), 70 + norm * 165, 0)
    rgb = np.zeros(grid.shape + (3,), dtype="uint8")
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 30, 95, 107
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([rgb, alpha.astype("uint8")]), "RGBA").save(
        path, "PNG", optimize=True)
    return int(np.isfinite(grid).sum())


def load_levels(cfg):
    """Serie de niveaux SWOT au site de reference."""
    path = ROOT / "data" / "swot_wse.json"
    if not path.exists():
        raise SystemExit("data/swot_wse.json absent : lancez "
                         "pipeline/update_swot.py")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scfg = cfg.get("scenarios") or {}
    wanted = scfg.get("wlvl_site")
    sites = [s for s in data.get("sites", []) if s.get("series")]
    site = next((s for s in sites if s["name"] == wanted),
                sites[0] if sites else None)
    if site is None:
        raise SystemExit("Aucune série SWOT exploitable.")
    offset = float(scfg.get("wlvl_offset", 0.0) or 0.0)
    return site, offset, data.get("demo", False)


def build(cfg, level=None, connected=True, out_path=OUT_FILE):
    index_path = ROOT / "data" / "scenarios.json"
    if not index_path.exists():
        raise SystemExit("Index absent : lancez pipeline/scenario_index.py")
    with open(index_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("demo"):
        raise SystemExit("Index de démonstration : relancez "
                         "pipeline/scenario_index.py")

    entry = next((s for s in idx["scenarios"]
                  if (s.get("files") or {}).get("wave")), None)
    if entry is None:
        raise SystemExit("Aucune sortie WAVE dans l'index.")

    scfg = cfg.get("scenarios") or {}
    centre = (cfg.get("lake") or {}).get("center") or {}
    zone = scfg.get("utm_zone") or geo.infer_zone(centre.get("lon", 137.5))
    south = scfg.get("southern_hemisphere", True)

    print(f"Bathymétrie : {entry['key']}")
    bed, areas, _ = hyp.bed_from_wave(entry["files"]["wave"],
                                      entry["params"]["wlvl"])
    print(f"  fond de {np.nanmin(bed):.2f} à {np.nanmax(bed):.2f} m · "
          f"{int(np.isfinite(bed).sum()):,} mailles")

    ds = sfield.open_dataset(entry["files"]["wave"])
    try:
        names = list(ds.variables)
        _, _, xv, yv, _, _ = sfield.read_coords(ds, names, z_shape=bed.shape)
    finally:
        ds.close()
    lon, lat = to_lonlat(xv, yv, zone, south)

    pad = 0.03
    bounds = (float(np.nanmin(lat)) - pad, float(np.nanmax(lat)) + pad,
              float(np.nanmin(lon)) - pad, float(np.nanmax(lon)) + pad)
    acfg = cfg.get("area") or {}
    from lake_area import grid_shape
    shape = grid_shape(bounds, float(acfg.get("map_resolution_m", 300.0)))

    if level is not None:
        wet, area, vol = extent_stats(bed, areas, level, connected)
        print(f"\nAu niveau {level:.2f} m : {area / 1e6:,.0f} km² · "
              f"{vol / 1e9:.3f} km³ · {int(wet.sum()):,} mailles")
        return None

    site, offset, demo = load_levels(cfg)
    print(f"Niveaux : {site['name']} · {len(site['series'])} observations"
          + (f" · décalage {offset:+.2f} m" if offset else
             " · AUCUN décalage de datum appliqué"))

    series = []
    for obs in site["series"]:
        h = obs["wse"] + offset
        wet, area, vol = extent_stats(bed, areas, h, connected)
        row = {"date": obs["date"][:10], "level_m": round(h, 3),
               "area_km2": round(area / 1e6, 1),
               "volume_km3": round(vol / 1e9, 4),
               "n_cells": int(wet.sum())}
        if wet.any():
            depth_map = np.where(wet, h - bed, np.nan)
            grid, _ = raster_mask(lon, lat, wet, depth_map, bounds, shape)
            if write_png(grid, MAP_DIR / f"{row['date']}.png"):
                row["map"] = f"extent_maps/{row['date']}.png"
        series.append(row)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "SWOT water level intersected with the Delft3D bathymetry; "
                  "only the pool hydraulically connected to the low point is "
                  "retained",
        "note": "SWOT measures elevation reliably; its per-pixel water "
                "classification is not robust over a salt playa, so the "
                "extent is derived from the level rather than read from the "
                "radar",
        "datum_note": "Bathymetry is AHD, SWOT levels are EGM2008 — "
                      f"scenarios.wlvl_offset applied: {offset:+.2f} m",
        "site": site["name"], "wlvl_offset": offset,
        "connected": bool(connected), "demo": bool(demo),
        "bathymetry": entry["key"],
        "map_bounds": [[bounds[0], bounds[2]], [bounds[1], bounds[3]]],
        "series": series,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nJSON écrit : {out_path} ({len(series)} dates)")
    for row in series[-5:]:
        print(f"  {row['date']}  {row['level_m']:7.2f} m -> "
              f"{row['area_km2']:8,.0f} km² · {row['volume_km3']:.3f} km³")
    if not offset:
        print("\nAucun décalage de datum n'est appliqué : les surfaces sont")
        print("comparables entre elles, mais leur niveau absolu reste à caler")
        print("(scenarios.wlvl_offset).")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Étendue de la nappe pour le niveau observé")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--level", type=float, default=None,
                        help="Calcule une seule étendue, sans écrire")
    parser.add_argument("--all-depressions", action="store_true",
                        help="Ne pas restreindre à la nappe connexe")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    build(cfg, level=args.level, connected=not args.all_depressions)


if __name__ == "__main__":
    main()
