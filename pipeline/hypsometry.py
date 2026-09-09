#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Courbe hypsometrique du lac, deduite de la bathymetrie Delft3D.

Sert de controle INDEPENDANT des surfaces mesurees par SWOT. Les deux
chaines n'ont rien en commun : l'une compte des mailles detectees en
eau par un radar, l'autre integre une surface sous un niveau donne.
Un accord entre elles est un argument solide ; un desaccord localise
la cause.

Le fond est reconstitue depuis une sortie WAVE :

    fond = wlvl - depth

ou wlvl est le niveau du scenario, lu dans le nom de fichier, et depth
la profondeur d'eau simulee. Un seul scenario suffit.

    python pipeline/hypsometry.py
    python pipeline/hypsometry.py --level -12.9

ATTENTION AU REFERENTIEL : la bathymetrie du modele est en AHD, tandis
que la WSE SWOT est en EGM2008. Comparer les deux sans appliquer
scenarios.wlvl_offset introduit un biais systematique — c'est
precisement ce que ce controle permet aussi de mettre en evidence.
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

import scenario_field as sfield  # noqa: E402

OUT_FILE = ROOT / "data" / "hypsometry.json"


def cell_areas(xv, yv):
    """Aire de chaque maille d'une grille curviligne, en m2.

    L'aire vaut le produit vectoriel des deux vecteurs tangents a la
    grille : |dP/di x dP/dj|. Sur une grille reguliere cela redonne le
    produit des pas, et le calcul reste juste sur une grille tournee ou
    etiree.
    """
    dxi = np.gradient(xv, axis=1)
    dyi = np.gradient(yv, axis=1)
    dxj = np.gradient(xv, axis=0)
    dyj = np.gradient(yv, axis=0)
    return np.abs(dxi * dyj - dyi * dxj)


def bed_from_wave(path, wlvl):
    """Altitude du fond et aire des mailles, depuis une sortie WAVE."""
    ds = sfield.open_dataset(path)
    try:
        depth, _, _, _ = sfield._read_2d(ds, "depth", -1, 0)
        names = list(ds.variables)
        xname, yname, xv, yv, _, _ = sfield.read_coords(ds, names,
                                                        z_shape=depth.shape)
        if xname is None:
            raise ValueError("Coordinates not found in this WAVE output.")
    finally:
        ds.close()

    wet = np.isfinite(depth) & (depth > 0) & np.isfinite(xv) & np.isfinite(yv)
    bed = np.where(wet, wlvl - depth, np.nan)
    return bed, cell_areas(xv, yv), wet


def curve(bed, areas, levels):
    """Surface et volume en fonction du niveau."""
    out = []
    flat_bed = bed[np.isfinite(bed)]
    flat_area = areas[np.isfinite(bed)]
    for h in levels:
        under = flat_bed <= h
        area = float(flat_area[under].sum())
        volume = float((flat_area[under] * (h - flat_bed[under])).sum())
        out.append({"level_m": round(float(h), 2),
                    "area_km2": round(area / 1e6, 1),
                    "volume_km3": round(volume / 1e9, 4)})
    return out


def area_at(rows, level):
    """Surface interpolee au niveau demande."""
    xs = [r["level_m"] for r in rows]
    ys = [r["area_km2"] for r in rows]
    return float(np.interp(level, xs, ys))


def build(cfg, level=None, out_path=OUT_FILE):
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

    wlvl = entry["params"].get("wlvl")
    if wlvl is None:
        raise SystemExit("Niveau du scénario introuvable dans son nom.")

    print(f"Bathymétrie reconstituée depuis {entry['key']}")
    bed, areas, wet = bed_from_wave(entry["files"]["wave"], wlvl)
    n = int(np.isfinite(bed).sum())
    print(f"  {n:,} mailles en eau · fond de {np.nanmin(bed):.2f} "
          f"à {np.nanmax(bed):.2f} m")

    lo = float(np.floor(np.nanmin(bed) * 2) / 2)
    hi = float(np.ceil(np.nanmax(bed) * 2) / 2)
    levels = np.arange(lo, hi + 0.25, 0.25)
    rows = curve(bed, areas, levels)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": entry["key"],
        "note": "Bed reconstructed as (scenario level - simulated depth); "
                "the model bathymetry is in AHD whereas SWOT levels are in "
                "EGM2008 — apply scenarios.wlvl_offset before comparing",
        "n_cells": n,
        "curve": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"\nJSON écrit : {out_path} ({len(rows)} niveaux)")

    for h in (-14.0, -13.5, -13.0, -12.5, -12.0, -11.0):
        if lo <= h <= hi:
            print(f"  {h:6.1f} m -> {area_at(rows, h):8.0f} km²")

    if level is not None:
        swot = area_at(rows, level)
        print(f"\nAu niveau observé {level:.2f} m : {swot:.0f} km² attendus "
              "par l'hypsométrie du modèle.")
        print("  Comparez à la surface mesurée par SWOT : un écart marqué "
              "signale\n  soit un décalage de datum, soit une "
              "sur-détection sur croûte de sel.")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Courbe hypsométrique depuis la bathymétrie Delft3D")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--level", type=float, default=None,
                        help="Niveau observé, pour comparaison directe")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    build(cfg, level=args.level)


if __name__ == "__main__":
    main()
