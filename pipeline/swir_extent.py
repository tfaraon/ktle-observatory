#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Etendue en eau : niveau SWOT contraint par l'observation SWIR.

La toolbox SWIR fournit, pour chaque scene Sentinel-2, un masque
classe (0 non-eau, 1 eau, 255 hors donnees) a 10 m. C'est une
observation OPTIQUE independante, insensible aux ambiguites de
retrodiffusion qui rendent la classification KaRIn fragile sur une
croute de sel. Elle joue ici le role que Sentinel-3 tient chez Rai et
al. (2026).

Trois usages, du plus simple au plus utile :

  1. VALIDATION. Comparer la surface deduite du niveau a la surface
     observee, et mesurer leur recouvrement (indice de Jaccard).

  2. CALAGE DU DATUM. La bathymetrie du modele est en AHD, la WSE SWOT
     en EGM2008 : leur ecart est inconnu et bloque toute comparaison
     absolue. Or le rivage observe par SWIR se trouve, par definition,
     au niveau reel de l'eau. Chercher le niveau qui reproduit au mieux
     ce rivage, puis le comparer a la WSE du jour, donne une estimation
     EMPIRIQUE de ce decalage — a partir des donnees, sans grille de
     geoide.

  3. CONTRAINTE. Restreindre l'etendue deduite du niveau aux zones que
     l'optique voit effectivement en eau.

    python pipeline/swir_extent.py --masks results_spit/masks
    python pipeline/swir_extent.py --masks results_spit/masks --apply
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
import water_extent as wex  # noqa: E402

OUT_FILE = ROOT / "data" / "swir_calibration.json"

CLASS_WATER = 1
CLASS_NODATA = 255


# ------------------------------------------------------------------
# Accord entre deux masques
# ------------------------------------------------------------------

def jaccard(a, b, valid=None):
    """Indice de Jaccard : intersection sur union.

    Plus severe qu'une simple comparaison de surfaces, qui pourrait
    concorder par compensation entre une zone manquante et une zone en
    trop.
    """
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    if valid is not None:
        v = np.asarray(valid, dtype=bool)
        a, b = a & v, b & v
    union = np.logical_or(a, b).sum()
    if not union:
        return None
    return float(np.logical_and(a, b).sum()) / float(union)


def best_level(bed, observed, valid, levels, connected=True):
    """Niveau reproduisant au mieux le rivage observe.

    Retourne (niveau, jaccard, courbe). La courbe permet de juger si
    l'optimum est franc ou plat : un maximum plat signale une rive en
    pente douce, ou le niveau est mal contraint.
    """
    curve = []
    top = (None, -1.0)
    for h in levels:
        wet = wex.flooded(bed, float(h), connected)
        score = jaccard(wet, observed, valid)
        if score is None:
            continue
        curve.append({"level_m": round(float(h), 3),
                      "jaccard": round(score, 4)})
        if score > top[1]:
            top = (float(h), score)
    return top[0], (top[1] if top[1] >= 0 else None), curve


def sharpness(curve, best, drop=0.05):
    """Largeur du plateau autour de l'optimum, en metres.

    Un optimum large signifie que plusieurs niveaux expliquent aussi
    bien le rivage : le calage est alors peu contraint, et il faut le
    dire plutot que de publier un chiffre unique.
    """
    if best is None or not curve:
        return None
    top = max(t["jaccard"] for t in curve)
    near = [t["level_m"] for t in curve if t["jaccard"] >= top - drop]
    return round(max(near) - min(near), 3) if near else None


# ------------------------------------------------------------------
# Lecture des masques de la toolbox SWIR
# ------------------------------------------------------------------

def read_mask(path):
    """Masque classe -> (eau, valide, lon, lat) echantillonne."""
    try:
        import rasterio
    except ImportError:
        raise RuntimeError("rasterio est requis pour lire les masques SWIR "
                           "(pip install rasterio).")

    with rasterio.open(str(path)) as ds:
        data = ds.read(1)
        transform = ds.transform
        crs = ds.crs
    water = data == CLASS_WATER
    valid = data != CLASS_NODATA
    return water, valid, transform, crs


def mask_lonlat(shape, transform, crs, step=5):
    """Coordonnees geographiques des pixels retenus, un sur `step`.

    Un masque Sentinel-2 compte des millions de pixels a 10 m ; un
    echantillonnage a 50 m suffit largement a caler un niveau et rend
    le calcul immediat.
    """
    ny, nx = shape
    rows = np.arange(0, ny, step)
    cols = np.arange(0, nx, step)
    cc, rr = np.meshgrid(cols, rows)
    # Centre des pixels
    x = transform.c + (cc + 0.5) * transform.a + (rr + 0.5) * transform.b
    y = transform.f + (cc + 0.5) * transform.d + (rr + 0.5) * transform.e

    zone = None
    try:
        epsg = crs.to_epsg()
        if epsg and 32700 <= epsg <= 32760:      # UTM sud WGS84
            zone = epsg - 32700
        elif epsg and 28300 <= epsg <= 28360:    # MGA94
            zone = epsg - 28300
    except Exception:
        zone = None
    if zone is None:
        raise ValueError(f"Fuseau UTM non déduit du CRS {crs}")

    lon, lat = geo.utm_to_lonlat_array(x, y, zone, south=True)
    return lon, lat, (rows, cols)


def sample_bed(lon, lat, model_lon, model_lat, bed):
    """Altitude du fond du modele, au droit des pixels SWIR.

    La bathymetrie varie lentement : le plus proche voisin suffit, et
    evite d'inventer du relief entre deux mailles du modele.
    """
    from scipy.spatial import cKDTree

    good = np.isfinite(model_lon) & np.isfinite(model_lat) & np.isfinite(bed)
    kx = np.cos(np.radians(float(np.nanmean(model_lat[good])))) or 1.0
    tree = cKDTree(np.column_stack([model_lon[good].ravel() * kx,
                                    model_lat[good].ravel()]))
    dist, idx = tree.query(np.column_stack([np.ravel(lon) * kx,
                                            np.ravel(lat)]),
                           distance_upper_bound=0.02)
    flat = bed[good].ravel()
    out = np.full(np.ravel(lon).shape, np.nan)
    inside = np.isfinite(dist)
    out[inside] = flat[idx[inside]]
    return out.reshape(np.shape(lon))


def mask_date(path):
    import re

    m = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", Path(path).name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# ------------------------------------------------------------------

def build(cfg, masks_dir, span=1.5, step_m=0.05, apply_offset=False,
          sample=5, out_path=OUT_FILE):
    masks = sorted(Path(masks_dir).expanduser().glob("*_water_class.tif"))
    if not masks:
        raise SystemExit(f"Aucun masque *_water_class.tif dans {masks_dir}")
    print(f"{len(masks)} masque(s) SWIR")

    index_path = ROOT / "data" / "scenarios.json"
    with open(index_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    entry = next((s for s in idx["scenarios"]
                  if (s.get("files") or {}).get("wave")), None)
    if entry is None:
        raise SystemExit("Aucune sortie WAVE dans l'index.")

    scfg = cfg.get("scenarios") or {}
    centre = (cfg.get("lake") or {}).get("center") or {}
    zone = scfg.get("utm_zone") or geo.infer_zone(centre.get("lon", 137.5))
    south = scfg.get("southern_hemisphere", True)

    bed_model, _, _ = hyp.bed_from_wave(entry["files"]["wave"],
                                        entry["params"]["wlvl"])
    ds = sfield.open_dataset(entry["files"]["wave"])
    try:
        _, _, xv, yv, _, _ = sfield.read_coords(ds, list(ds.variables),
                                                z_shape=bed_model.shape)
    finally:
        ds.close()
    model_lon, model_lat = geo.utm_to_lonlat_array(xv, yv, zone, south)

    site, current_offset, _ = wex.load_levels(cfg)
    levels_by_date = {o["date"][:10]: o["wse"] for o in site["series"]}
    print(f"Niveaux : {site['name']} · {len(levels_by_date)} dates")

    rows = []
    for path in masks:
        date = mask_date(path)
        if date is None or date not in levels_by_date:
            continue
        wse = levels_by_date[date]

        water, valid, transform, crs = read_mask(path)
        lon, lat, (rr, cc) = mask_lonlat(water.shape, transform, crs, sample)
        obs = water[np.ix_(rr, cc)]
        ok = valid[np.ix_(rr, cc)]
        bed_s = sample_bed(lon, lat, model_lon, model_lat, bed_model)
        ok = ok & np.isfinite(bed_s)
        if ok.sum() < 500:
            continue

        pixel_m2 = abs(transform.a * transform.e) * sample * sample
        obs_area = float(obs[ok].sum()) * pixel_m2

        levels = np.arange(wse - span, wse + span + step_m / 2, step_m)
        h_star, score, curve = best_level(bed_s, obs, ok, levels)
        if h_star is None:
            continue

        at_swot = wex.flooded(bed_s, wse + current_offset)
        rows.append({
            "date": date,
            "swot_level_m": round(wse, 3),
            "swir_area_km2": round(obs_area / 1e6, 1),
            "model_area_km2": round(float(at_swot[ok].sum()) * pixel_m2 / 1e6,
                                    1),
            "best_level_m": round(h_star, 3),
            "implied_offset_m": round(h_star - wse, 3),
            "jaccard": round(score, 4),
            "plateau_m": sharpness(curve, h_star),
            "n_samples": int(ok.sum()),
        })
        r = rows[-1]
        print(f"  {date}  SWIR {r['swir_area_km2']:7,.0f} km² · "
              f"modèle {r['model_area_km2']:7,.0f} km² · "
              f"décalage {r['implied_offset_m']:+.2f} m · "
              f"Jaccard {r['jaccard']:.2f}")

    if not rows:
        raise SystemExit("Aucune date commune entre masques SWIR et série "
                         "SWOT.")

    offsets = [r["implied_offset_m"] for r in rows]
    median = float(np.median(offsets))
    spread = float(np.percentile(offsets, 75) - np.percentile(offsets, 25))
    scores = [r["jaccard"] for r in rows]

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "Optical SWIR waterline (Sentinel-2) compared with the "
                  "extent implied by the SWOT level and the model "
                  "bathymetry; the level best reproducing the observed "
                  "shoreline gives an empirical datum offset",
        "site": site["name"],
        "applied_offset_m": current_offset,
        "median_offset_m": round(median, 3),
        "offset_iqr_m": round(spread, 3),
        "median_jaccard": round(float(np.median(scores)), 4),
        "n_dates": len(rows),
        "dates": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nJSON écrit : {out_path}")
    print(f"\nDécalage de datum estimé : {median:+.2f} m "
          f"(écart interquartile {spread:.2f} m sur {len(rows)} dates)")
    print(f"Recouvrement médian : {np.median(scores):.2f}")
    if spread > 0.3:
        print("\nDispersion notable : les dates ne s'accordent pas bien. "
              "Vérifiez le seuil\nSWIR, la qualité des scènes, et la "
              "concordance des dates avec les passes SWOT.")
    print("\nÀ reporter dans config.yaml si l'estimation vous convainc :")
    print(f"  scenarios.wlvl_offset: {median:+.2f}")

    if apply_offset:
        cfg_path = ROOT / "config.yaml"
        text = cfg_path.read_text(encoding="utf-8")
        text = text.replace(f"  wlvl_offset: {current_offset}",
                            f"  wlvl_offset: {median:+.2f}", 1)
        cfg_path.write_text(text, encoding="utf-8")
        print(f"\nconfig.yaml mis à jour : wlvl_offset = {median:+.2f}")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Étendue SWIR + SWOT, et calage du datum")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--masks", required=True,
                        help="Dossier masks/ produit par la toolbox SWIR")
    parser.add_argument("--span", type=float, default=1.5,
                        help="Demi-plage de recherche du niveau, en m")
    parser.add_argument("--step", type=float, default=0.05,
                        help="Pas de recherche, en m")
    parser.add_argument("--sample", type=int, default=5,
                        help="Sous-échantillonnage des pixels SWIR")
    parser.add_argument("--apply", action="store_true",
                        help="Écrire le décalage médian dans config.yaml")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    build(cfg, args.masks, span=args.span, step_m=args.step,
          apply_offset=args.apply, sample=args.sample)


if __name__ == "__main__":
    main()
