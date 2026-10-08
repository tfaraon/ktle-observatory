#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refuse de publier une serie plus courte que celle deja en ligne.

Les chaines SWOT sont incrementales : leur memoire est un cache, et la
serie complete n'est plus deductible des granules presents. Si ce cache
est perdu, ignore ou invalide par erreur, le calcul aboutit quand meme —
sur les seuls granules du jour — et ecrase des annees d'observations sans
le moindre message d'erreur. C'est le scenario que ce controle arrete.

Il compare chaque fichier a la version versionnee (git show HEAD:...) et
echoue si le nombre d'observations a baisse. Une serie identique ou plus
longue passe. Un fichier nouveau passe aussi : il n'y a rien a perdre.

Usage :
    python tools/check_series.py site/data/lake_area.json \
                                 site/data/swot_wse.json
    python tools/check_series.py --ref origin/main site/data/*.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def count_observations(payload):
    """Nombre total d'observations, quelle que soit la forme du JSON.

    lake_area et water_extent exposent une liste « series » a la racine ;
    swot_wse en expose une par site. Plutot que de coder ces deux formes,
    on additionne toutes les listes nommees « series » rencontrees : une
    troisieme forme sera comptee sans retoucher ce fichier.
    """
    total = 0
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "series" and isinstance(value, list):
                    total += len(value)
                else:
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return total


def committed(path, ref="HEAD"):
    """Version versionnee d'un fichier, ou None s'il n'y en a pas."""
    try:
        out = subprocess.run(
            ["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True,
            capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return json.loads(out.stdout.decode("utf-8"))
    except ValueError:
        return None


def check(paths, ref="HEAD"):
    """Retourne la liste des regressions : (chemin, avant, apres)."""
    losses = []
    for path in paths:
        local = ROOT / path
        if not local.exists():
            print(f"  {path} : absent, ignoré")
            continue
        try:
            now = count_observations(
                json.loads(local.read_text(encoding="utf-8")))
        except ValueError as e:
            losses.append((path, None, f"illisible ({e})"))
            continue
        old = committed(path, ref)
        if old is None:
            print(f"  {path} : {now} observations (nouveau)")
            continue
        before = count_observations(old)
        verdict = "OK" if now >= before else "RÉGRESSION"
        print(f"  {path} : {before} → {now} observations  {verdict}")
        if now < before:
            losses.append((path, before, now))
    return losses


def main():
    parser = argparse.ArgumentParser(
        description="Vérifie qu'aucune série publiée ne raccourcit")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--ref", default="HEAD",
                        help="Référence Git de comparaison (défaut : HEAD)")
    args = parser.parse_args()

    print(f"Comparaison avec {args.ref} :")
    losses = check(args.paths, args.ref)
    if losses:
        print("\nPublication annulée : une série a raccourci.")
        for path, before, now in losses:
            print(f"  {path} : {before} → {now}")
        print("\nCause la plus probable : le cache incrémental n'a pas été")
        print("lu (KTLE_STATE_DIR absent, state/ non versionné) ou un")
        print("paramètre de méthode a changé. Vérifiez avant de forcer.")
        return 1
    print("Aucune régression.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
