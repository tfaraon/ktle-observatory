#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Controle de l'archive Delft3D : repere les runs incomplets avant de
lancer un traitement long.

Ne lit que les en-tetes (dimensions et variables), jamais les tableaux
de donnees : le balayage des 790 runs prend quelques minutes la ou un
compactage complet demande plusieurs heures.

Un run est signale s'il lui manque une variable attendue, si l'une de
ses dimensions est vide, ou si sa structure s'ecarte de la majorite —
en pratique, une simulation interrompue avant la fin ecrit moins de pas
de temps que les autres.

Usage :
    python pipeline/check_runs.py                # rapport
    python pipeline/check_runs.py --csv bad.csv  # export des runs suspects
    python pipeline/check_runs.py --quiet        # code retour uniquement
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import scenario_field as sfield  # noqa: E402

INDEX_FILE = ROOT / "data" / "scenarios.json"

# Variables sans lesquelles le site ne peut rien afficher
REQUIRED = {
    "flow": ("U1", "V1"),
    "wave": ("hsign", "wlength", "period", "dir"),
}


def inspect(path, source):
    """En-tete d'un fichier -> dict decrivant sa structure.

    Retourne aussi les problemes constates : variable manquante,
    dimension vide, fichier illisible.
    """
    info = {"path": str(path), "source": source, "problems": [],
            "dims": {}, "n_time": None, "n_layer": None}
    try:
        ds = sfield.open_dataset(path)
    except Exception as e:
        info["problems"].append(f"illisible ({type(e).__name__})")
        return info

    try:
        names = {n.lower() for n in ds.variables}
        # netCDF4 expose des objets Dimension, d'autres lecteurs de
        # simples entiers : accepter les deux.
        info["dims"] = {d: (int(v) if isinstance(v, int) else int(len(v)))
                        for d, v in ds.dimensions.items()}

        for dim, size in info["dims"].items():
            if size == 0:
                info["problems"].append(f"dimension '{dim}' vide")

        for var in REQUIRED[source]:
            if var.lower() not in names:
                info["problems"].append(f"variable '{var}' absente")

        for dim, size in info["dims"].items():
            if sfield.is_time_dim(dim):
                info["n_time"] = size
            elif sfield.is_layer_dim(dim):
                info["n_layer"] = size

        # Un fichier dont les tableaux ne sont pas ecrits jusqu'au bout
        # se voit a une forme incoherente avec ses dimensions declarees
        for var in REQUIRED[source]:
            real = next((n for n in ds.variables if n.lower() == var.lower()),
                        None)
            if real is None:
                continue
            shape = tuple(int(s) for s in ds.variables[real].shape)
            if 0 in shape:
                info["problems"].append(f"'{real}' de forme {shape}")
    except Exception as e:
        info["problems"].append(f"lecture de l'en-tête : {type(e).__name__}")
    finally:
        ds.close()
    return info


def scan(scenarios, progress=True):
    reports = []
    total = len(scenarios)
    for n, entry in enumerate(scenarios):
        rec = {"key": entry["key"], "problems": [], "files": {}}
        for source in ("flow", "wave"):
            path = (entry.get("files") or {}).get(source)
            if not path:
                rec["problems"].append(f"sortie {source.upper()} absente")
                continue
            if not Path(path).exists():
                rec["problems"].append(f"fichier {source.upper()} introuvable")
                continue
            info = inspect(path, source)
            rec["files"][source] = info
            rec["problems"] += [f"{source.upper()} : {p}"
                                for p in info["problems"]]
        reports.append(rec)
        if progress and ((n + 1) % 100 == 0 or n + 1 == total):
            print(f"  {n + 1}/{total} runs examinés")
    return reports


def majority_shape(reports, source, key):
    """Valeur la plus frequente d'une dimension (la structure normale)."""
    counts = Counter(r["files"][source][key] for r in reports
                     if source in r["files"]
                     and r["files"][source].get(key) is not None)
    return counts.most_common(1)[0][0] if counts else None


def main():
    parser = argparse.ArgumentParser(
        description="Contrôle de l'archive Delft3D")
    parser.add_argument("--index", default=str(INDEX_FILE))
    parser.add_argument("--csv", default=None,
                        help="Exporte les runs suspects dans ce fichier")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    with open(args.index, "r", encoding="utf-8") as f:
        idx = json.load(f)
    if idx.get("demo"):
        raise SystemExit("Index de démonstration : lancez d'abord "
                         "python pipeline/scenario_index.py")

    scen = idx["scenarios"][:args.limit] if args.limit else idx["scenarios"]
    if not args.quiet:
        print(f"Examen de {len(scen)} runs (en-têtes seulement)…")
    reports = scan(scen, progress=not args.quiet)

    # Structure de reference : celle de la majorite des runs
    ref = {}
    for source in ("flow", "wave"):
        ref[source] = {k: majority_shape(reports, source, k)
                       for k in ("n_time", "n_layer")}

    odd = []
    for rec in reports:
        for source, info in rec["files"].items():
            for k, label in (("n_time", "pas de temps"),
                             ("n_layer", "couche(s)")):
                expected = ref[source].get(k)
                got = info.get(k)
                if expected and got is not None and got != expected:
                    rec["problems"].append(
                        f"{source.upper()} : {got} {label} au lieu de "
                        f"{expected}")
        if rec["problems"]:
            odd.append(rec)

    if not args.quiet:
        print(f"\nStructure de référence :")
        for source in ("flow", "wave"):
            r = ref[source]
            if r.get("n_time"):
                print(f"  {source.upper()} : {r['n_time']} pas de temps"
                      + (f", {r['n_layer']} couches" if r.get("n_layer")
                         else ""))

        if not odd:
            print(f"\nAucune anomalie sur {len(reports)} runs.")
        else:
            print(f"\n{len(odd)} run(s) suspect(s) sur {len(reports)} :")
            for rec in odd[:20]:
                print(f"  {rec['key']}")
                for p in rec["problems"]:
                    print(f"      {p}")
            if len(odd) > 20:
                print(f"  … et {len(odd) - 20} autre(s)")
            print("\nCes runs seront ignorés par le compactage (signalés et "
                  "laissés vides).")
            print("Une sortie tronquée signale souvent une simulation qui "
                  "n'a pas convergé : il vaut la peine de vérifier le "
                  "fichier .tri-diag correspondant.")

    if args.csv and odd:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["key", "problems"])
            for rec in odd:
                w.writerow([rec["key"], " ; ".join(rec["problems"])])
        if not args.quiet:
            print(f"\nExport : {args.csv}")

    return 1 if odd else 0


if __name__ == "__main__":
    sys.exit(main())
