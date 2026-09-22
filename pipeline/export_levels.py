#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serie de niveaux SWOT au format de la toolbox SWIR.

Le telechargement CSV du site est concu comme une archive documentee :
lignes de metadonnees precedees de #, plusieurs sites, colonne date_utc.
La toolbox SWIR attend autre chose : un seul niveau par date, dans deux
colonnes date et water_level_m, sans commentaire — pd.read_csv lit les
lignes # comme des donnees et echoue sur la premiere ligne reelle.

    python pipeline/export_levels.py --out niveaux_swir.csv
    python pipeline/export_levels.py --site "Madigan Gulf" --out mg.csv
    python pipeline/export_levels.py --apply-offset --out niveaux_ahd.csv

Les niveaux sont exportes en EGM2008, tels que SWOT les fournit.
--apply-offset ajoute scenarios.wlvl_offset, pour les ramener au
referentiel de la bathymetrie une fois le decalage etabli.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent


def daily_levels(series):
    """Un niveau par jour : moyenne des passes d'une meme journee.

    Deux passes le meme jour donneraient deux lignes de meme date, que
    la toolbox ne saurait departager.
    """
    by_day = {}
    for obs in series:
        if obs.get("wse") is None:
            continue
        by_day.setdefault(obs["date"][:10], []).append(float(obs["wse"]))
    return [(day, float(np.mean(v)), len(v)) for day, v in sorted(by_day.items())]


def write(rows, path, offset=0.0):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "water_level_m"])
        for day, level, _ in rows:
            w.writerow([day, f"{level + offset:.3f}"])
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Niveaux SWOT au format de la toolbox SWIR")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--site", default=None,
                        help="Site SWOT (défaut : scenarios.wlvl_site)")
    parser.add_argument("--out", required=True, help="Fichier CSV à écrire")
    parser.add_argument("--apply-offset", action="store_true",
                        help="Ajouter scenarios.wlvl_offset aux niveaux")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    scfg = cfg.get("scenarios") or {}

    src = ROOT / "data" / "swot_wse.json"
    if not src.exists():
        sys.exit("data/swot_wse.json absent : lancez pipeline/update_swot.py")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("demo"):
        sys.exit("Série de démonstration : relancez pipeline/update_swot.py")

    wanted = args.site or scfg.get("wlvl_site")
    sites = {s["name"]: s for s in data.get("sites", [])}
    if wanted not in sites:
        sys.exit(f"Site « {wanted} » absent. Disponibles : "
                 + ", ".join(sites))

    offset = float(scfg.get("wlvl_offset", 0.0) or 0.0) if args.apply_offset \
        else 0.0
    rows = daily_levels(sites[wanted]["series"])
    out = write(rows, args.out, offset)

    merged = sum(1 for _, _, n in rows if n > 1)
    print(f"{out} : {len(rows)} dates, site {wanted}")
    if merged:
        print(f"  {merged} journée(s) à plusieurs passes, moyennées")
    print("  Référentiel : "
          + (f"EGM2008 + décalage {offset:+.2f} m" if offset else "EGM2008"))


if __name__ == "__main__":
    main()
