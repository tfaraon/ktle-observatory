#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Surface en eau de Kati Thanda - Lake Eyre a partir de SWOT.

Methode d'apres :

    Rai, A.K., Cohen, T.J., Armon, M., Marx, S.K. (2026). Volumetric
    analysis of a playa lake using SWOT data: An improved understanding
    of the inflows to Kati Thanda-Lake Eyre. Journal of Hydrology, 676,
    135652. https://doi.org/10.1016/j.jhydrol.2026.135652
    (acces libre, licence CC BY)

adaptee au produit L2 HR Raster.

Ce que reprend cette implementation :
  - filtres qualite sur la detection d'eau (fraction d'eau bornee,
    drapeau de qualite) ;
  - filtre median 5x5 pour supprimer les detections isolees, le bruit
    de speckle etant important sur une croute de sel ;
  - agregation a 100 m ;
  - surface = somme des aires d'eau des mailles retenues ;
  - propagation d'incertitude en somme quadratique (Eq. 10 de
    l'article).

Ce qui differe, et pourquoi :
  - L'article travaille sur le nuage de points PIXC ; on utilise ici le
    produit Raster, deja agrege a 100 m. Les auteurs jugent le Raster
    « pas ideal » pour ce lac, notamment pour la couverture ; le
    controle de couverture ci-dessous repond a cette reserve.
  - L'article contraint SWOT par un masque optique Sentinel-3 OLCI
    (MNDWI), car croute de sel humide et eau tres peu profonde ont des
    retrodiffusions voisines (0-15 dB). Ce masque n'est pas disponible
    ici : on le remplace par une emprise geographique — le domaine
    Delft3D, qui EST le lac. C'est une contrainte spatiale, non
    spectrale : elle ecarte les detections hors du lac mais ne separe
    pas l'eau tres peu profonde du sel sature a l'interieur. La surface
    est donc plutot un majorant, et l'incertitude reelle depasse les
    ~15 % rapportes par l'article avec la fusion Sentinel-3.

Usage :
    python pipeline/lake_area.py            # -> data/lake_area.json
    python pipeline/lake_area.py --limit 5  # essai rapide
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import geo  # noqa: E402

OUT_FILE = ROOT / "data" / "lake_area.json"
CACHE_FILE = ROOT / "data" / "area_cache.json"

# Valeurs par defaut, reprises de l'article
DEFAULTS = {
    "water_frac_range": [0.1, 0.99],   # Fig. 4 : fraction d'eau retenue
    "max_qual": 1,                     # 0 = bon, 1 = suspect
    "median_size": 5,                  # filtre median 5x5 (Eq. 2)
    "resolution": "100",               # agregation a 100 m
    "min_coverage": 0.15,              # passage juge trop partiel en deca
}


def open_dataset(path):
    """Ouverture NetCDF (import paresseux, isole pour les tests)."""
    try:
        from netCDF4 import Dataset
    except ImportError:
        raise RuntimeError("netCDF4 is not installed (pip install netCDF4) — "
                           "required to read SWOT granules.")
    return Dataset(str(path), "r")


# ------------------------------------------------------------------
# Coeur de la methode : masque d'eau
# ------------------------------------------------------------------

def median_filter_mask(mask, size=5):
    """Filtre median sur un masque booleen (Eq. 2 de l'article).

    Une maille est conservee si la majorite de son voisinage est en
    eau. Cela supprime les detections isolees — speckle sur croute de
    sel — sans eroder les rives, la ou un simple seuillage laisserait
    un semis de faux positifs.
    """
    if not size or size < 2:
        return mask
    from scipy.ndimage import uniform_filter

    frac = uniform_filter(mask.astype("float64"), size=int(size),
                          mode="nearest")
    return frac > 0.5


def water_mask(water_frac, qual=None, frac_range=(0.1, 0.99), max_qual=1,
               median_size=5):
    """Mailles retenues comme etant en eau.

    La borne basse ecarte les mailles majoritairement seches, la borne
    haute les mailles saturees a 1.0, souvent issues d'une detection
    degradee plutot que d'une eau franche.
    """
    lo, hi = frac_range
    frac = np.asarray(water_frac, dtype="float64")
    mask = np.isfinite(frac) & (frac >= lo) & (frac <= hi)
    if qual is not None:
        q = np.asarray(qual)
        mask &= np.isfinite(q) & (q <= max_qual)
    return median_filter_mask(mask, median_size)


def area_from_arrays(water_area, water_frac, qual=None, uncert=None,
                     inside=None, cell_area=None, **kw):
    """Surface en eau d'une scene, en m2.

    water_area est l'aire d'eau par maille fournie par le produit ; a
    defaut, elle est reconstituee comme fraction x aire de maille.
    inside restreint le calcul a l'emprise du lac.
    """
    mask = water_mask(water_frac, qual, **kw)
    if inside is not None:
        mask &= np.asarray(inside, dtype=bool)

    if water_area is not None:
        area = np.asarray(water_area, dtype="float64")
        area = np.where(np.isfinite(area), area, 0.0)
    elif cell_area is not None:
        area = np.asarray(water_frac, dtype="float64") * float(cell_area)
        area = np.where(np.isfinite(area), area, 0.0)
    else:
        raise ValueError("water_area or cell_area is required")

    total = float(area[mask].sum())

    # Somme quadratique : les erreurs de maille sont supposees
    # independantes, comme la propagation de l'Eq. 10.
    if uncert is not None:
        u = np.asarray(uncert, dtype="float64")
        u = np.where(np.isfinite(u), u, 0.0)
        sigma = float(np.sqrt((u[mask] ** 2).sum()))
    else:
        sigma = None

    return {"area_m2": total, "uncert_m2": sigma,
            "n_cells": int(mask.sum()),
            "n_valid": int(np.isfinite(np.asarray(water_frac)).sum())}


# ------------------------------------------------------------------
# Emprise du lac (remplace la contrainte optique Sentinel-3)
# ------------------------------------------------------------------

def model_boundary(cfg):
    """Points du domaine Delft3D, en degres — l'emprise du lac.

    Le domaine du modele epouse le lac : il fournit une contrainte
    spatiale a defaut du masque optique de l'article.
    """
    import scenario_field as sfield

    scfg = cfg.get("scenarios") or {}
    index_path = ROOT / "data" / "scenarios.json"
    if not index_path.exists():
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("demo") or not idx.get("scenarios"):
        return None

    entry = next((s for s in idx["scenarios"] if "wave" in (s.get("files") or {})),
                 None)
    if entry is None:
        return None

    zone = scfg.get("utm_zone") or geo.infer_zone(
        ((cfg.get("lake") or {}).get("center") or {}).get("lon", 137.5))
    south = scfg.get("southern_hemisphere", True)

    ds = sfield.open_dataset(entry["files"]["wave"])
    try:
        xname, yname, xv, yv, _, _ = sfield.read_coords(ds, list(ds.variables))
        if xname is None:
            return None
        good = np.isfinite(xv) & np.isfinite(yv)
        pts = np.column_stack([xv[good].ravel(), yv[good].ravel()])
    finally:
        ds.close()

    lonlat = np.array([geo.utm_to_lonlat(float(a), float(b), zone, south)
                       for a, b in pts])
    return lonlat


def inside_boundary(lon, lat, boundary, tol_km=2.0):
    """Mailles situees dans l'emprise, au sens du plus proche voisin.

    tol_km absorbe l'ecart entre la grille du modele et celle de SWOT ;
    une valeur trop large reintegrerait des detections hors du lac.
    """
    from scipy.spatial import cKDTree

    if boundary is None:
        return None
    lat0 = float(np.nanmean(boundary[:, 1]))
    kx = math.cos(math.radians(lat0)) or 1.0
    tree = cKDTree(np.column_stack([boundary[:, 0] * kx, boundary[:, 1]]))

    pts = np.column_stack([np.ravel(lon) * kx, np.ravel(lat)])
    tol_deg = tol_km / 111.32
    dist, _ = tree.query(pts, distance_upper_bound=tol_deg)
    return np.isfinite(dist).reshape(np.shape(lon))


# ------------------------------------------------------------------
# Lecture d'un granule
# ------------------------------------------------------------------

def _get(ds, *names):
    lower = {n.lower(): n for n in ds.variables}
    for n in names:
        real = lower.get(n.lower())
        if real:
            return np.ma.filled(np.ma.masked_array(
                ds.variables[real][:]).astype("float64"), np.nan)
    return None


_BBOX_CACHE = {}


def granule_zone(ds, default=53):
    """Fuseau UTM declare par le granule."""
    crs = ds.variables.get("crs")
    for attr in ("utm_zone_num", "utm_zone", "zone"):
        value = getattr(crs, attr, None) if crs is not None else None
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return default


def boundary_utm_bbox(boundary, zone, south=True, pad=5000.0):
    """Cadre du lac en coordonnees du fuseau demande, avec marge.

    Sert de rejet prealable : inutile de reprojeter 1,6 million de
    mailles pour decouvrir qu'un granule ne touche pas le lac.
    """
    key = (zone, south, round(pad))
    if key in _BBOX_CACHE:
        return _BBOX_CACHE[key]
    ex, ny = geo.lonlat_to_utm_array(boundary[:, 0], boundary[:, 1], zone,
                                     south)
    box = (float(ex.min()) - pad, float(ex.max()) + pad,
           float(ny.min()) - pad, float(ny.max()) + pad)
    _BBOX_CACHE[key] = box
    return box


def granule_lonlat(ds, zone=None, south=True):
    """Coordonnees geographiques des mailles du granule.

    Le produit Raster est en UTM ; le fuseau est lu dans l'attribut
    de projection quand il est present.
    """
    x = _get(ds, "x")
    y = _get(ds, "y")
    if x is None or y is None:
        return None, None
    if zone is None:
        zone = 53
        crs = ds.variables.get("crs")
        for attr in ("utm_zone_num", "utm_zone", "zone"):
            value = getattr(crs, attr, None) if crs is not None else None
            if value is not None:
                try:
                    zone = int(value)
                    break
                except (TypeError, ValueError):
                    pass
    xx, yy = np.meshgrid(np.ravel(x), np.ravel(y))
    return geo.utm_to_lonlat_array(xx, yy, zone, south)


def read_granule(path, boundary=None, params=None, zone=None, south=True,
                 want_mask=False):
    """Surface en eau d'un granule, ou None si inexploitable."""
    params = dict(DEFAULTS, **(params or {}))
    ds = open_dataset(path)
    try:
        gz = granule_zone(ds, zone or 53)

        # Rejets prealables, avant toute lecture lourde. Le repertoire
        # de telechargement peut contenir des scenes d'autres regions :
        # un ecart de fuseau les ecarte immediatement.
        if boundary is not None:
            lake_zone = zone or geo.infer_zone(float(boundary[:, 0].mean()))
            if abs(gz - lake_zone) > 1:
                return {"area_m2": 0.0, "uncert_m2": None, "n_cells": 0,
                        "n_valid": 0, "covered_cells": 0}

        x = _get(ds, "x")
        y = _get(ds, "y")
        sub_y = sub_x = slice(None)
        if boundary is not None and x is not None and y is not None:
            xmin, xmax, ymin, ymax = boundary_utm_bbox(boundary, gz, south)
            kx = np.where((x >= xmin) & (x <= xmax))[0]
            ky = np.where((y >= ymin) & (y <= ymax))[0]
            if not kx.size or not ky.size:
                return {"area_m2": 0.0, "uncert_m2": None, "n_cells": 0,
                        "n_valid": 0, "covered_cells": 0}
            sub_y = slice(int(ky[0]), int(ky[-1]) + 1)
            sub_x = slice(int(kx[0]), int(kx[-1]) + 1)

        def sub(name):
            arr = _get(ds, name)
            return None if arr is None else arr[sub_y, sub_x]

        frac = sub("water_frac")
        if frac is None:
            return None
        area = sub("water_area")
        qual = sub("water_area_qual")
        uncert = sub("water_area_uncert")

        inside = None
        covered = None
        lon = lat = None
        if boundary is not None:
            xx, yy = np.meshgrid(x[sub_x], y[sub_y])
            lon, lat = geo.utm_to_lonlat_array(xx, yy, gz, south)
            if lon is not None:
                inside = inside_boundary(lon, lat, boundary)
                covered = int((inside & np.isfinite(frac)).sum())

        result = area_from_arrays(
            area, frac, qual, uncert, inside,
            frac_range=tuple(params["water_frac_range"]),
            max_qual=params["max_qual"],
            median_size=params["median_size"])
        result["covered_cells"] = covered
        if lon is not None:
            keep = water_mask(frac, qual,
                              frac_range=tuple(params["water_frac_range"]),
                              max_qual=params["max_qual"],
                              median_size=params["median_size"])
            if inside is not None:
                keep &= inside
            result["mask"] = (lon, lat, frac, area, keep)
        return result
    finally:
        ds.close()


# ------------------------------------------------------------------
# Traitement parallele
# ------------------------------------------------------------------

_WORKER = {}


def _init_worker(boundary, params, zone, south, want_mask):
    """Contexte d'un processus fils.

    L'emprise du lac compte des dizaines de milliers de points : la
    transmettre une fois par processus, et non par granule, evite de la
    serialiser des centaines de fois.
    """
    _WORKER.update(boundary=boundary, params=params, zone=zone,
                   south=south, want_mask=want_mask)


def _process_one(path):
    """Un granule, dans un processus fils. Les erreurs sont renvoyees
    plutot que levees : un fichier corrompu ne doit pas interrompre le
    traitement des centaines d'autres."""
    try:
        res = read_granule(path, _WORKER["boundary"], _WORKER["params"],
                           _WORKER["zone"], _WORKER["south"],
                           _WORKER["want_mask"])
        return path, res, None
    except Exception as e:
        return path, None, f"{type(e).__name__}: {e}"[:100]


# ------------------------------------------------------------------
# Masque spatial : un raster lon/lat par date
# ------------------------------------------------------------------

def new_accumulator(size):
    """Grilles cumulees d'une date."""
    z = lambda: np.zeros((size, size))          # noqa: E731
    return {"frac": z(), "area": z(), "wet": z(), "scene": z()}


def accumulate_mask(acc, lon, lat, frac, area, wet, bounds):
    """Ajoute une scene aux grilles cumulees de la date.

    Deux passes (394 et 435) peuvent imager le lac le meme jour et se
    recouvrir. Sommer leurs surfaces compterait l'eau deux fois : on
    accumule donc sur une grille lon/lat commune, en retenant combien
    de scenes ont vu chaque case en eau, pour en faire la moyenne
    plutot que la somme.
    """
    lat0, lat1, lon0, lon1 = bounds
    ny, nx = acc["frac"].shape
    sel = np.ravel(wet)
    if not sel.any():
        return
    la = np.ravel(lat)[sel]
    lo = np.ravel(lon)[sel]
    fr = np.nan_to_num(np.ravel(frac)[sel])
    ar = (np.nan_to_num(np.ravel(area)[sel]) if area is not None
          else np.zeros(fr.shape))

    keep = (la >= lat0) & (la <= lat1) & (lo >= lon0) & (lo <= lon1)
    if not keep.any():
        return
    iy = np.clip(((la[keep] - lat0) / (lat1 - lat0) * (ny - 1)).round()
                 .astype(int), 0, ny - 1)
    ix = np.clip(((lo[keep] - lon0) / (lon1 - lon0) * (nx - 1)).round()
                 .astype(int), 0, nx - 1)

    np.add.at(acc["frac"], (iy, ix), fr[keep])
    np.add.at(acc["area"], (iy, ix), ar[keep])
    np.add.at(acc["wet"], (iy, ix), 1)
    # Une scene ne compte qu'une fois par case, quel que soit le nombre
    # de mailles sources qui y tombent.
    touched = np.zeros((ny, nx), dtype=bool)
    touched[iy, ix] = True
    acc["scene"] += touched


def area_from_accumulator(acc):
    """Surface en eau de la date, en m2, sans double comptage.

    Chaque case vaut la moyenne des estimations des scenes qui l'ont
    vue en eau, et non leur somme.
    """
    scenes = np.maximum(acc["scene"], 1)
    per_cell = np.where(acc["wet"] > 0, acc["area"] / scenes, 0.0)
    return float(per_cell.sum()), int((acc["wet"] > 0).sum())


def write_mask_png(acc, path, colour=(30, 95, 107)):
    """Raster de fraction d'eau -> PNG bleu, transparent hors de l'eau.

    L'opacite suit la fraction d'eau : une rive a demi inondee apparait
    plus pale qu'un plan d'eau franc, ce qu'un masque binaire cacherait.
    """
    from PIL import Image

    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(acc["wet"] > 0,
                        acc["frac"] / np.maximum(acc["wet"], 1), np.nan)
    frac = frac[::-1, :]                    # latitude croissante -> haut
    alpha = np.where(np.isfinite(frac), np.clip(frac, 0, 1) * 205, 0)
    rgb = np.zeros(frac.shape + (3,), dtype="uint8")
    for k, v in enumerate(colour):
        rgb[..., k] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([rgb, alpha.astype("uint8")]), "RGBA").save(
        path, "PNG", optimize=True)
    return int(np.isfinite(frac).sum())


def boundary_bounds(boundary, pad=0.05):
    """Cadre lon/lat commun a toutes les dates, deduit de l'emprise."""
    if boundary is None:
        return None
    return (float(boundary[:, 1].min()) - pad, float(boundary[:, 1].max()) + pad,
            float(boundary[:, 0].min()) - pad, float(boundary[:, 0].max()) + pad)


# ------------------------------------------------------------------
# Assemblage de la serie
# ------------------------------------------------------------------

def granule_datetime(name):
    import re

    m = re.search(r"(\d{8}T\d{6})", os.path.basename(name))
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S") if m else None


def combine_scenes(scenes, boundary_cells=None, min_coverage=0.15):
    """Somme les scenes d'un meme passage.

    Les scenes du produit Raster ne se recouvrent pas (128 x 128 km),
    leurs surfaces s'additionnent donc. Un passage ne couvrant qu'une
    partie du lac est signale : sans ce controle, une couverture
    partielle se lirait comme un assechement, defaut que l'article
    releve explicitement pour octobre 2024.
    """
    total = sum(s["area_m2"] for s in scenes)
    sig = [s["uncert_m2"] for s in scenes if s.get("uncert_m2") is not None]
    uncert = math.sqrt(sum(u ** 2 for u in sig)) if sig else None
    covered = sum(s.get("covered_cells") or 0 for s in scenes)

    coverage = None
    if boundary_cells:
        coverage = covered / float(boundary_cells)

    return {
        "area_km2": round(total / 1e6, 3),
        "uncert_km2": round(uncert / 1e6, 3) if uncert is not None else None,
        "n_scenes": len(scenes),
        "n_cells": sum(s["n_cells"] for s in scenes),
        "coverage": round(coverage, 3) if coverage is not None else None,
        "partial": bool(coverage is not None and coverage < min_coverage),
    }


def relative_volume_error(depth_error, area_error):
    """Eq. 10 de l'article : erreur relative sur le volume.

    Les erreurs relatives sur la profondeur et sur la surface se
    combinent en somme quadratique.
    """
    return math.sqrt(depth_error ** 2 + area_error ** 2)


def build(cfg, limit=None, out_path=OUT_FILE):
    import scenarios as _  # noqa: F401  (verifie l'arborescence du projet)
    from update_swot import list_nc_files, resolve_path

    acfg = dict(DEFAULTS, **(cfg.get("area") or {}))
    swot_dir = resolve_path(cfg["paths"]["swot_data"])
    resolution = acfg.get("resolution")
    files = list_nc_files(str(swot_dir), resolution)
    if not files:
        # Distinguer les trois causes : sans cela, « aucun granule »
        # ne dit pas s'il faut monter un disque, corriger un chemin ou
        # relacher le filtre de resolution.
        if not swot_dir.exists():
            raise SystemExit(
                f"Répertoire introuvable : {swot_dir}\n"
                "Le disque externe est-il monté ? Sinon, corrigez "
                "paths.swot_data dans config.yaml.")
        every = list_nc_files(str(swot_dir))
        if not every:
            raise SystemExit(
                f"Aucun fichier .nc sous {swot_dir}\n"
                "Lancez d'abord : python pipeline/update_swot.py --download")
        raise SystemExit(
            f"{len(every)} granule(s) présents, mais aucun ne correspond à "
            f"la résolution « {resolution} ».\n"
            f"  exemple de nom : {os.path.basename(every[0])}\n"
            "Ajustez area.resolution dans config.yaml (null = toutes).")
    if limit:
        files = files[:limit]

    boundary = None
    if acfg.get("boundary", "model") == "model":
        boundary = model_boundary(cfg)
        if boundary is None:
            print("Emprise du modèle indisponible : calcul sur le granule "
                  "entier, la surface sera surestimée.")
    boundary_cells = len(boundary) if boundary is not None else None

    scfg = cfg.get("scenarios") or {}
    zone = scfg.get("utm_zone")
    south = scfg.get("southern_hemisphere", True)

    map_bounds = boundary_bounds(boundary)
    map_size = int(acfg.get("map_size", 420))
    want_mask = map_bounds is not None      # requis aussi pour la surface
    maps = {}          # date -> grilles cumulees

    by_date = {}
    failures = []
    outside = 0        # granules ne recoupant pas le lac
    workers = acfg.get("workers")
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)
    workers = max(1, min(int(workers), len(files)))

    def results():
        """Granules traites, en parallele au-dela d'un worker."""
        if workers == 1:
            for path in files:
                yield _process_one_local(path)
            return
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(
                max_workers=workers, initializer=_init_worker,
                initargs=(boundary, acfg, zone, south, want_mask)) as pool:
            for out in pool.map(_process_one, files, chunksize=4):
                yield out

    def _process_one_local(path):
        try:
            return path, read_granule(path, boundary, acfg, zone, south,
                                      want_mask), None
        except Exception as e:
            return path, None, f"{type(e).__name__}: {e}"[:100]

    print(f"Traitement de {len(files)} granules sur {workers} processus…")
    for n, (path, res, err) in enumerate(results()):
        when = granule_datetime(path)
        if when is None:
            continue
        if err:
            failures.append((os.path.basename(path), err))
            continue
        if res and (res.get("covered_cells") or res["n_cells"]):
            day = when.strftime("%Y-%m-%d")
            by_date.setdefault(day, []).append(res)
            if want_mask and res.get("mask"):
                if day not in maps:
                    maps[day] = new_accumulator(map_size)
                accumulate_mask(maps[day], *res["mask"], map_bounds)
            res.pop("mask", None)
        elif res:
            # Le repertoire de telechargement peut contenir des granules
            # d'autres zones : ils sont ecartes par l'emprise du lac.
            outside += 1
        if (n + 1) % 20 == 0 or n + 1 == len(files):
            print(f"  {n + 1}/{len(files)} granules")

    map_dir = out_path.parent / "area_maps"
    n_overlap = 0
    series = []
    for day in sorted(by_date):
        entry = combine_scenes(by_date[day], boundary_cells,
                               acfg.get("min_coverage", 0.15))
        entry["date"] = day
        if day in maps:
            # Surface issue de la grille fusionnee : une case vue par
            # deux passes n'est comptee qu'une fois.
            merged, n_cells = area_from_accumulator(maps[day])
            overlap = float((maps[day]["scene"] > 1).sum())
            entry["scene_area_km2"] = entry["area_km2"]
            entry["area_km2"] = round(merged / 1e6, 3)
            entry["overlap_cells"] = int(overlap)
            if entry["scene_area_km2"] and overlap:
                inflate = entry["scene_area_km2"] / max(entry["area_km2"], 1e-9)
                if inflate > 1.02:
                    n_overlap += 1
            if write_mask_png(maps[day], map_dir / f"{day}.png"):
                entry["map"] = f"area_maps/{day}.png"
        series.append(entry)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "Rai et al. (2026) — adapted to the SWOT L2 HR Raster "
                  "product",
        "citation": "Rai, A.K., Cohen, T.J., Armon, M. & Marx, S.K. (2026). "
                    "Volumetric analysis of a playa lake using SWOT data: an "
                    "improved understanding of the inflows to Kati "
                    "Thanda-Lake Eyre. Journal of Hydrology 676, 135652.",
        "doi": "10.1016/j.jhydrol.2026.135652",
        "note": "Spatial constraint from the Delft3D domain replaces the "
                "Sentinel-3 optical mask; the area is an upper bound",
        "uncertainty_note": "uncert_km2 is the quadrature sum of per-cell "
                            "uncertainties reported by the product. It is a "
                            "formal precision, not a validated accuracy: the "
                            "source paper reports ~15 % error against optical "
                            "water masks, several orders of magnitude larger",
        "parameters": {k: acfg[k] for k in
                       ("water_frac_range", "max_qual", "median_size",
                        "resolution", "min_coverage") if k in acfg},
        "n_granules": len(files),
        "map_bounds": ([[map_bounds[0], map_bounds[2]],
                        [map_bounds[1], map_bounds[3]]]
                       if map_bounds else None),
        "series": series,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\nJSON écrit : {out_path} ({len(series)} dates)")
    for e in series[-5:]:
        flag = "  (couverture partielle)" if e["partial"] else ""
        print(f"  {e['date']}  {e['area_km2']:>8.1f} km²"
              + (f" ± {e['uncert_km2']:.1f}" if e["uncert_km2"] else "")
              + flag)
    if n_overlap:
        print(f"  {n_overlap} date(s) avec recouvrement entre passes : "
              "la surface est calculée sur la grille fusionnée, pas en "
              "sommant les scènes")
    if outside:
        print(f"  {outside} granule(s) hors de l'emprise du lac, ignoré(s)")
    if failures:
        print(f"  {len(failures)} granule(s) illisible(s), ex. {failures[0]}")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Surface en eau SWOT (méthode Rai et al. 2026)")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None,
                        help="Processus parallèles (défaut : cœurs - 1)")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if args.workers is not None:
        cfg.setdefault("area", {})["workers"] = args.workers
    build(cfg, limit=args.limit)


if __name__ == "__main__":
    main()
