#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exporte un site statique, deployable sur GitHub Pages.

Un navigateur ne sait ni lire un NetCDF ni interpoler : on pre-calcule
donc, pour chaque scenario et chaque couche, exactement ce que l'API
renvoie aujourd'hui — une image georeferencee et un jeu de fleches.
Le site n'a plus alors qu'a poser l'image sur la carte, ce qu'il fait
deja.

    python pipeline/export_static.py                 # -> site/
    python pipeline/export_static.py --limit 20      # essai rapide
    python pipeline/export_static.py --colors 0      # sans quantification

Ce qui reste identique : niveaux SWOT, serie temporelle, imagerie GIBS,
meteo (rafraichie par l'action GitHub), appariement des scenarios et
frise temporelle — l'appariement est refait en JavaScript a partir du
meme index.

Ce qui disparait : le bouton de mise a jour (il n'y a plus de serveur).
Le pipeline tourne en local et l'on publie le resultat.
"""

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import compact_store  # noqa: E402
import geo  # noqa: E402
import scenario_field as sfield  # noqa: E402

SITE = ROOT / "site"

# Meme rampe que le frontend, pour un rendu identique
TURBO = [(0.00, (48, 18, 59)), (0.13, (65, 69, 171)), (0.25, (70, 117, 237)),
         (0.38, (57, 162, 252)), (0.50, (27, 207, 212)), (0.63, (98, 252, 107)),
         (0.75, (210, 233, 53)), (0.88, (254, 155, 45)), (0.96, (234, 74, 19)),
         (1.00, (122, 4, 3))]
ALPHA = 205


def turbo_rgb(t):
    """Valeurs normalisees [0,1] -> RGB, comme turboColour() cote client."""
    t = np.clip(np.nan_to_num(t, nan=0.0), 0.0, 1.0)
    xs = np.array([a for a, _ in TURBO])
    cs = np.array([c for _, c in TURBO], dtype="float64")
    return np.stack([np.interp(t, xs, cs[:, k]) for k in range(3)], axis=-1)


def raster_png(z, vmin, vmax, path, colors=64):
    """Champ 2D -> PNG transparent hors du lac.

    La quantification des couleurs reduit fortement la taille sans
    difference visible (1 niveau RGB sur 255 en moyenne a 64 couleurs).
    """
    from PIL import Image

    arr = np.array([[np.nan if v is None else v for v in row] for row in z],
                   dtype="float64")
    # La latitude croit vers le haut, les lignes d'une image vers le bas
    arr = arr[::-1, :]
    span = (vmax - vmin) or 1.0
    rgb = turbo_rgb((arr - vmin) / span).astype("uint8")
    alpha = np.where(np.isfinite(arr), ALPHA, 0).astype("uint8")

    if colors:
        img = Image.fromarray(rgb, "RGB").quantize(
            colors=int(colors), method=Image.MEDIANCUT).convert("RGB")
        rgb = np.array(img)

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(
        path, "PNG", optimize=True)
    return path.stat().st_size


def arrow_grid(payload):
    """Grille reguliere sur laquelle les fleches sont echantillonnees.

    Elle ne depend que de l'emprise et de la densite, donc elle est
    identique pour tous les scenarios d'une meme source : on la stocke
    une seule fois dans le manifeste, et chaque scenario ne conserve
    que les indices occupes.
    """
    (lat0, lon0), (lat1, lon1) = payload["bounds"]
    return {"lat0": lat0, "lat1": lat1, "lon0": lon0, "lon1": lon1}


def pack_arrows(payload, n):
    """Fleches -> indices sur la grille reguliere + azimut + valeur.

    La grille des fleches suit `extent` (emprise des points), et non
    `bounds` (cadre de l'image, plus large d'une demi-maille).
    """
    a = payload["arrows"]
    if not a["lat"]:
        return {"i": [], "b": [], "v": []}
    (lat0, lon0), (lat1, lon1) = payload["extent"]
    # Les positions viennent d'un linspace sur l'emprise : on retrouve
    # l'indice par simple regle de trois.
    span_lat = (lat1 - lat0) or 1.0
    span_lon = (lon1 - lon0) or 1.0
    idx, bear, val = [], [], []
    for la, lo, b, v in zip(a["lat"], a["lon"], a["bearing"], a["value"]):
        iy = int(round((la - lat0) / span_lat * (n - 1)))
        ix = int(round((lo - lon0) / span_lon * (n - 1)))
        idx.append(iy * n + ix)
        bear.append(round(float(b), 1))
        val.append(round(float(v), 4))
    return {"i": idx, "b": bear, "v": val}


def layer_jobs(cfg, layer_indices):
    """Couches a produire : (identifiant fichier, couche, indice vertical)."""
    jobs = []
    for name, spec in sfield.MAP_LAYERS.items():
        if spec["mode"] == "vector":
            for k in range(len(layer_indices)):
                jobs.append((f"{name}_{k}", name, k))
        else:
            jobs.append((name, name, 0))
    return jobs


def render(store, cfg, key, entry, layer, layer_index, common):
    """Charge utile d'une couche, depuis le fichier compact ou le NetCDF."""
    if store is not None and store.has(key):
        try:
            return store.map_layer(key, layer=layer, layer_index=layer_index,
                                   **common)
        except Exception:
            pass
    spec = sfield.MAP_LAYERS[layer]
    path = (entry.get("files") or {}).get(spec["source"])
    if not path:
        raise ValueError(f"no {spec['source'].upper()} output for {key}")
    scfg = cfg.get("scenarios") or {}
    centre = (cfg.get("lake") or {}).get("center") or {}
    zone = scfg.get("utm_zone") or geo.infer_zone(centre.get("lon", 137.5))
    return sfield.read_map_layer(
        path, layer=layer, zone=zone,
        south=scfg.get("southern_hemisphere", True),
        time_index=scfg.get("time_index", -1),
        layer_index=layer_index,
        rotate=scfg.get("rotate_vectors", True), **common)


def global_scales(store, cfg, scen, jobs, common, sample=40):
    """Bornes de couleur communes a tous les scenarios.

    Fixer l'echelle rend les couleurs comparables d'un scenario a
    l'autre — indispensable des lors qu'on parcourt la frise
    temporelle. Les couches dont la borne est deja imposee dans
    config.yaml gardent leur valeur.
    """
    scfg = cfg.get("scenarios") or {}
    configured = scfg.get("layer_scales") or {}
    step = max(1, len(scen) // max(1, sample))
    probe = scen[::step][:sample]

    scales = {}
    for file_id, layer, lidx in jobs:
        lo, hi = (configured.get(layer) or [None, None])[:2]
        if lo is not None and hi is not None:
            scales[file_id] = [float(lo), float(hi)]
            continue
        maxima = []
        for entry in probe:
            try:
                out = render(store, cfg, entry["key"], entry, layer, lidx,
                             common)
            except Exception:
                continue
            if out.get("zmax") is not None:
                maxima.append(out["zmax"])
        if maxima:
            # 95e centile : une valeur aberrante isolee ne doit pas
            # ecraser toute la palette
            hi_auto = float(np.percentile(maxima, 95))
        else:
            hi_auto = 1.0
        scales[file_id] = [float(lo or 0.0),
                           float(hi if hi is not None else hi_auto)]
    return scales


def build(cfg, out_dir=SITE, colors=64, limit=None, sample=40):
    from PIL import Image  # noqa: F401  (verifie la dependance tot)

    index_path = ROOT / "data" / "scenarios.json"
    if not index_path.exists():
        raise SystemExit("Index absent : lancez pipeline/scenario_index.py")
    with open(index_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("demo"):
        raise SystemExit("L'index chargé est celui de démonstration : "
                         "relancez pipeline/scenario_index.py")

    scen = idx["scenarios"]
    if limit:
        scen = scen[:limit]

    scfg = cfg.get("scenarios") or {}
    n_arrows = int(scfg.get("arrow_density", 26))
    common = dict(grid_res=scfg.get("map_grid_res", 260),
                  n_arrows=n_arrows,
                  smooth=scfg.get("current_smooth", 2.0),
                  wave_dir_convention=scfg.get("wave_dir_convention", "from"))

    store = None
    compact_file = ROOT / "data" / "compact.nc"
    if compact_file.exists():
        try:
            store = compact_store.CompactStore(compact_file)
            print(f"Fichier compact : {len(store.keys)} scénarios")
        except Exception as e:
            print(f"Fichier compact inutilisable ({e}) — lecture des NetCDF")

    layer_indices = (store.layers if store is not None
                     else [scfg.get("layer_index", 0)])
    jobs = layer_jobs(cfg, layer_indices)
    print(f"{len(scen)} scénarios × {len(jobs)} couches = "
          f"{len(scen) * len(jobs)} rendus")

    print("\nCalcul des bornes de couleur communes…")
    scales = global_scales(store, cfg, scen, jobs, common, sample)
    for file_id, (lo, hi) in scales.items():
        print(f"  {file_id:14s} {lo:g} – {hi:g}")

    out_dir = Path(out_dir)
    img_dir = out_dir / "img"
    arr_dir = out_dir / "layers"
    for d in (img_dir, arr_dir):
        d.mkdir(parents=True, exist_ok=True)

    bounds, extents, total_bytes, failures = {}, {}, 0, []
    t0 = time.time()

    for n, entry in enumerate(scen):
        key = entry["key"]
        per_scenario = {}
        for file_id, layer, lidx in jobs:
            try:
                lo, hi = scales[file_id]
                out = render(store, cfg, key, entry, layer, lidx,
                             dict(common, vmin=lo, vmax=hi))
            except Exception as e:
                failures.append((key, file_id, f"{type(e).__name__}: {e}"[:90]))
                continue
            src = sfield.MAP_LAYERS[layer]["source"]
            bounds.setdefault(src, out["bounds"])
            extents.setdefault(src, out["extent"])
            total_bytes += raster_png(out["z"], lo, hi,
                                      img_dir / f"{key}__{file_id}.png",
                                      colors=colors)
            per_scenario[file_id] = pack_arrows(out, n_arrows)
            per_scenario[file_id]["zmax"] = out.get("zmax")

        with open(arr_dir / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(per_scenario, f, separators=(",", ":"))

        if (n + 1) % 20 == 0 or n + 1 == len(scen):
            done = n + 1
            rate = (time.time() - t0) / done
            eta = rate * (len(scen) - done)
            print(f"  {done}/{len(scen)} scénarios · {total_bytes / 1e6:.0f} Mo"
                  f" · reste ~{eta / 60:.0f} min")

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_scenarios": len(scen),
        "bounds": bounds,
        "extent": extents,
        "n_arrows": n_arrows,
        "scales": scales,
        "layer_indices": [int(t) + 1 for t in layer_indices],
        "n_layers_source": int(getattr(store.ds, "n_layers_source", 0) or 0)
                           if store is not None else 0,
        "layers": [{"id": k, "label": v["label"], "units": v["units"],
                    "source": v["source"], "mode": v["mode"]}
                   for k, v in sfield.MAP_LAYERS.items()],
        "matching": {
            "weights": scfg.get("weights") or {},
            "normalize": scfg.get("normalize", "range"),
            "wlvl_rounding": scfg.get("wlvl_rounding", "nearest"),
            "wind_station": scfg.get("wind_station"),
            "wind_dir_convention": scfg.get("wind_dir_convention", "from"),
            "wlvl_offset": scfg.get("wlvl_offset", 0.0),
            "wlvl_site": scfg.get("wlvl_site"),
            "salinity": scfg.get("salinity"),
        },
        "imagery": cfg.get("imagery") or {},
        "lake": cfg.get("lake") or {},
        "datum_label": (cfg.get("display") or {}).get("datum_label", "WSE (m)"),
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    # Index allege : le site n'a besoin que des cles et des parametres,
    # jamais des chemins absolus du disque.
    slim = {"n_scenarios": len(scen),
            "grid": idx.get("grid", {}),
            "units": idx.get("units", {}),
            "labels": idx.get("labels", {}),
            "scenarios": [{"key": s["key"], "params": s["params"]}
                          for s in scen]}
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / "scenarios.json", "w", encoding="utf-8") as f:
        json.dump(slim, f, separators=(",", ":"))

    for name in ("swot_wse.json", "weather.json"):
        src_file = ROOT / "data" / name
        if src_file.exists():
            shutil.copy(src_file, data_dir / name)

    for name in ("index.html", "style.css", "app.js", "methods.js",
                 "windrose.js", "download.js"):
        shutil.copy(ROOT / "frontend" / name, out_dir / name)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    site_size = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    print(f"\nSite écrit : {out_dir}")
    print(f"  images   : {total_bytes / 1e6:.0f} Mo")
    print(f"  total    : {site_size / 1e6:.0f} Mo "
          f"({site_size / 1024 / 1024 / 1024 * 100:.0f} % de la limite 1 Go)")
    if failures:
        print(f"  {len(failures)} rendu(s) en échec :")
        for key, file_id, msg in failures[:5]:
            print(f"    {key} [{file_id}] {msg}")
    if store is not None:
        store.close()
    return out_dir


def main():
    parser = argparse.ArgumentParser(description="Export d'un site statique")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--out", default=str(SITE))
    parser.add_argument("--colors", type=int, default=64,
                        help="Quantification des couleurs (0 = aucune)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Ne traiter que les N premiers scénarios")
    parser.add_argument("--sample", type=int, default=40,
                        help="Scénarios échantillonnés pour les bornes")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    build(cfg, out_dir=Path(args.out), colors=args.colors, limit=args.limit,
          sample=args.sample)


if __name__ == "__main__":
    main()
