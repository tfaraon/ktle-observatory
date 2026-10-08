#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pourquoi la serie WSE a change de longueur.

Depuis que la serie est reassemblee depuis le cache et non depuis les
granules presents sur le disque, son compte peut bouger pour trois
raisons tres differentes, et le journal de update.sh ne permet pas de
les distinguer :

  1. doublons : le meme granule present dans deux sous-repertoires de
     l'archive comptait deux fois dans l'ancienne methode ;
  2. granules effaces de l'archive mais toujours dans le cache : ils
     reviennent dans la serie ;
  3. filtre IQR : il s'applique a la serie entiere (tous les granules
     portent pass/resolution/tile « Unknown », donc un seul groupe), si
     bien qu'ajouter des points deplace les bornes et peut en rejeter
     d'autres.

Ce script lit le cache et la liste des fichiers, sans ouvrir aucun
granule, et calcule les deux series — ancienne methode et nouvelle —
pour montrer laquelle des trois raisons agit.

Usage :
    python tools/diagnose_wse.py
    python tools/diagnose_wse.py --config autre.yaml
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import update_swot as us          # noqa: E402


def rows_from(names, known, on_disk):
    """Lignes de serie, sans relire aucun granule."""
    rows = []
    for name in names:
        rec = known.get(os.path.basename(name))
        if rec and rec.get("wse") is not None:
            rows.append({
                "date": datetime.strptime(rec["date"], us.CACHE_DATE_FMT),
                "wse": rec["wse"],
                "filename": on_disk.get(os.path.basename(name), name),
                "pass": "Unknown", "resolution": "Unknown", "tile": "Unknown",
            })
    return rows


def counts(rows, ex, site):
    """Longueur de la serie : brute, apres bornes, telle que publiee.

    La derniere colonne passe par dataframe_to_records, donc par la
    fenetre extraction.date_min / date_max : sans elle, les chiffres ne
    sont pas comparables a ceux de swot_wse.json.
    """
    import pandas as pd

    cols = ["date", "wse", "filename", "pass", "resolution", "tile"]
    df = pd.DataFrame(rows, columns=cols)
    before = len(df)
    bounded = us.apply_post_filters(df.copy(), ex.get("filter_bound", False),
                                    False)
    full = us.apply_post_filters(df.copy(), ex.get("filter_bound", False),
                                 ex.get("filter_outliers", False))
    published = us.dataframe_to_records(
        full, date_min=ex.get("date_min"), date_max=ex.get("date_max"),
        datum_offset=site.get("datum_offset", 0.0))
    return before, len(bounded), len(full), len(published)


def main():
    parser = argparse.ArgumentParser(
        description="Explique un changement de longueur de la série WSE")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ex = cfg["extraction"]

    archive = us.swot_dir(cfg)
    cache_path = us.state_file(
        "extraction_cache.json",
        cfg["paths"].get("cache", "data/extraction_cache.json"))
    cache = us.load_cache(cache_path)

    print(f"Cache    : {cache_path}")
    print(f"Archive  : {archive}"
          + ("" if archive.exists() else "   (ABSENTE)"))

    files = (us.list_nc_files(str(archive), ex.get("filter_resolution"))
             if archive.exists() else [])
    base = [os.path.basename(p) for p in files]
    distinct = set(base)
    print(f"Fichiers : {len(files)} chemins, {len(distinct)} noms distincts"
          + (f"  → {len(base) - len(distinct)} DOUBLONS" if len(base) > len(distinct)
             else ""))
    if len(base) > len(distinct):
        seen, dupes = set(), []
        for b in base:
            if b in seen:
                dupes.append(b)
            seen.add(b)
        for d in sorted(set(dupes))[:10]:
            where = [p for p in files if os.path.basename(p) == d]
            print(f"    {d}")
            for w in where:
                print(f"      {w}")

    on_disk = {os.path.basename(p): p for p in files}

    for site in cfg["sites"]:
        key = us.site_key(site)
        entry = (cache.get("sites") or {}).get(key) or {}
        known = entry.get("files") or {}
        if not known:
            print(f"\n=== {site['name']} : aucune entrée de cache "
                  f"(clé {key}) ===")
            continue

        with_wse = {n for n, r in known.items()
                    if r and r.get("wse") is not None}
        apple = {n for n in known if n.startswith("._")}
        orphans = sorted(set(known) - distinct - apple)

        # Acquisitions connues sous plusieurs versions de traitement
        by_acq = {}
        for n in known:
            if n in apple:
                continue
            by_acq.setdefault(us.acquisition_key(n), []).append(n)
        multi = {k: v for k, v in by_acq.items() if len(v) > 1}

        print(f"\n=== {site['name']} ===")
        print(f"  cache      : {len(known)} entrées, {len(with_wse)} avec WSE, "
              f"{len(known) - len(with_wse)} sans (hors du site ou illisible)")
        print(f"  AppleDouble: {len(apple)} entrée(s) « ._ », jamais un granule")
        print(f"  hors disque: {len(orphans)} entrée(s) de cache sans fichier")
        print(f"  acquisitions en double version : {len(multi)}")
        for k, v in list(multi.items())[:3]:
            print(f"      {k[-46:]}")
            for n in sorted(v):
                tag = "sur disque" if n in on_disk else "cache seul"
                print(f"        {us.version_rank(n) or '(sans version)'}"
                      f"  {tag}")

        old = counts(rows_from(base, known, on_disk), ex, site)
        naive = counts(rows_from(sorted(known), known, on_disk), ex, site)
        sel = counts([r for r in rows_from(
            [n for n, _ in us.select_records(known, on_disk)], known, on_disk)],
            ex, site)
        for label, c in (("archive seule (avant hier)", old),
                         ("cache brut (hier, défaillant)", naive),
                         ("cache trié par acquisition", sel)):
            print(f"  {label:<30}: {c[0]} lignes → {c[1]} bornes → "
                  f"{c[2]} IQR → {c[3]} publiées")

        verdict = []
        if len(base) > len(distinct):
            verdict.append("doublons de chemin dans l'archive")
        if apple:
            verdict.append(f"{len(apple)} AppleDouble dans le cache")
        if multi:
            verdict.append(f"{len(multi)} survol(s) présents sous deux "
                           "versions du produit")
        if orphans and not multi:
            verdict.append(f"{len(orphans)} granule(s) effacé(s) du disque")
        print("  cause      : "
              + ("; ".join(verdict) if verdict else "aucun écart"))

    print("\nLa colonne « publiées » est ce que compte le garde-fou.")
    print("La dernière ligne est ce que produit la version actuelle du code.")
    print("Si elle rejoint « archive seule », le tri par acquisition a")
    print("réparé l'écart. python pipeline/update_swot.py --prune-cache")
    print("retire ensuite du cache ce qu'il ne sert plus à rien de garder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
