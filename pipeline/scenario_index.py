#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construit l'index des scenarios Delft3D a partir des noms de fichiers
et l'ecrit dans data/scenarios.json (servi ensuite par le site).

Usage :
    python pipeline/scenario_index.py            # indexe le repertoire
    python pipeline/scenario_index.py --list     # affiche la grille
    python pipeline/scenario_index.py --demo     # index synthetique
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import yaml

from scenarios import (PARAM_SPECS, build_grid, build_regex, design_coverage,
                       read_design, scan_directory)

INDEX_FILE = ROOT / "data" / "scenarios.json"


def fmt(v):
    """1.0 -> '1_0' (convention de nommage des sorties)."""
    return f"{v:.1f}".replace(".", "_")


def make_demo_scenarios():
    """Echantillon synthetique respectant la convention de nommage."""
    import random

    rng = random.Random(7)
    out = []
    for _ in range(200):
        sp = float(rng.randint(1, 35))
        di = float(rng.choice([0, 45, 90, 135, 180, 225, 270, 315]))
        wl = -14.0 + 0.5 * rng.randint(0, 15)
        sal = float(rng.choice([0, 50, 100, 150, 200, 250]))
        key = (f"wind-sp{fmt(sp)}_wind-dir{fmt(di)}"
               f"_wlvl{fmt(wl)}_sal{fmt(sal)}")
        out.append({
            "key": key,
            "files": {"wave": f"<demo>/Output/Wave/wave_{key}.nc",
                      "flow": f"<demo>/Output/Flow/{key}.nc"},
            "params": {"wind_speed": sp, "wind_dir": di,
                       "wlvl": wl, "salinity": sal},
        })
    # dedoublonnage sur la signature de parametres
    seen, uniq = set(), []
    for s in out:
        if s["key"] not in seen:
            seen.add(s["key"]); uniq.append(s)
    return sorted(uniq, key=lambda s: s["key"])


def build(cfg, demo=False):
    scfg = cfg.get("scenarios") or {}
    regexes = build_regex(wlvl_sign=scfg.get("wlvl_sign", "negative"))

    if demo:
        scenarios = make_demo_scenarios()
        report = {"unnamed": [], "junk": [], "bad_format": []}
        directory = "<demo>"
    else:
        directory = scfg.get("directory")
        if not directory:
            raise ValueError("config scenarios.directory manquant.")
        directory = str(Path(directory).expanduser())
        scenarios, report = scan_directory(
            directory, regexes,
            verify_format=scfg.get("verify_format", True))

    grid = build_grid(scenarios)

    # Comparaison au plan d'experience, si fourni
    coverage = None
    design_path = scfg.get("design_csv")
    if design_path and not demo:
        design_path = Path(design_path).expanduser()
        if design_path.exists():
            coverage = design_coverage(read_design(design_path), scenarios)
            coverage["file"] = str(design_path)
        else:
            print(f"Note : plan d'experience introuvable ({design_path})")

    n_wave = sum(1 for s in scenarios if "wave" in s["files"])
    n_flow = sum(1 for s in scenarios if "flow" in s["files"])

    payload = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo": bool(demo),
        "directory": directory,
        "n_scenarios": len(scenarios),
        "n_wave": n_wave,
        "n_flow": n_flow,
        "coverage": coverage,
        "grid": grid,
        "units": {k: v[1] for k, v in PARAM_SPECS.items()},
        "labels": {k: v[2] for k, v in PARAM_SPECS.items()},
        "skipped": {k: v[:10] for k, v in report.items()},
        "n_skipped": {k: len(v) for k, v in report.items()},
        "scenarios": scenarios,
    }

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def describe(payload):
    print(f"Index ecrit : {INDEX_FILE}")
    print(f"  Repertoire : {payload['directory']}")
    print(f"  Scenarios  : {payload['n_scenarios']} "
          f"({payload.get('n_wave', 0)} WAVE, {payload.get('n_flow', 0)} FLOW)")
    for key, vals in payload["grid"].items():
        unit = payload["units"].get(key, "")
        head = ", ".join(f"{v:g}" for v in vals[:8])
        more = f" ... (+{len(vals) - 8})" if len(vals) > 8 else ""
        print(f"  {payload['labels'][key]:<20} {len(vals):>3} valeurs : "
              f"{head}{more} {unit}")
    expected = 1
    for vals in payload["grid"].values():
        expected *= len(vals)
    if expected != payload["n_scenarios"]:
        pct = 100.0 * payload["n_scenarios"] / expected if expected else 0
        print(f"  Plan lacunaire : {payload['n_scenarios']} runs pour "
              f"{expected} combinaisons possibles ({pct:.1f} %) — "
              "l'appariement prend le plus proche disponible.")

    cov = payload.get("coverage")
    if cov:
        print(f"\n  Plan d'experience : {cov['n_design_unique']} runs prevus, "
              f"{cov['n_done']} presents, {cov['n_missing']} manquants")
        for row in cov["missing_sample"][:5]:
            vals = ", ".join(f"{k}={v:g}" for k, v in row.items())
            print(f"    manquant : {vals}")
        if cov["n_extra"]:
            print(f"  {cov['n_extra']} run(s) hors plan :")
            for k in cov["extra_sample"][:3]:
                print(f"    {k}")
    sk = payload["n_skipped"]
    if isinstance(sk, dict):
        if sk.get("junk"):
            print(f"\n  Fichiers systeme macOS ignores : {sk['junk']}")
            print("    (fichiers ._* crees en copiant depuis macOS vers un "
                  "volume exFAT/FAT ;")
            print("     pour les supprimer du disque : dot_clean -m "
                  "/chemin/vers/Output)")
        if sk.get("bad_format"):
            print(f"  Fichiers a l'entete NetCDF invalide : {sk['bad_format']}")
            for name in payload["skipped"]["bad_format"][:5]:
                print(f"    {name}")
        if sk.get("unnamed"):
            print(f"  Noms non conformes : {sk['unnamed']}")
            for name in payload["skipped"]["unnamed"][:5]:
                print(f"    {name}")


def main():
    parser = argparse.ArgumentParser(description="Index des scenarios Delft3D")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--list", action="store_true",
                        help="Affiche la grille sans reconstruire")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.list and INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            describe(json.load(f))
        return

    describe(build(cfg, demo=args.demo))


if __name__ == "__main__":
    main()
