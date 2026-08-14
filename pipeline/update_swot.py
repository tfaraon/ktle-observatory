#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline SWOT -> JSON pour l'observatoire Kati Thanda - Lake Eyre.

Enchaine :
  1. (optionnel, --download) recherche et telechargement des SEULS
     granules plus recents que le dernier granule local (earthaccess) ;
  2. extraction incrementale des series WSE : seuls les nouveaux
     fichiers NetCDF sont traites (cache), via le worker _process_file
     de SWOT_toolbox, puis filtres bornes / outliers identiques a
     extract_wse_timeseries_parallel ;
  3. ecriture du JSON servi par le site (series + derniere observation
     + fraicheur des donnees).

Usage :
    python pipeline/update_swot.py                  # extraction incrementale
    python pipeline/update_swot.py --download       # nouveaux granules + extraction
    python pipeline/update_swot.py --demo           # donnees synthetiques
    python pipeline/update_swot.py --rebuild-cache  # retraite tous les fichiers
    python pipeline/update_swot.py --no-cache       # extract_wse_timeseries_parallel
                                                    # d'origine (verification croisee)
"""

import argparse
import json
import math
import multiprocessing
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # rend SWOT_toolbox importable

import yaml

GRANULE_DATE_RE = re.compile(r"(\d{8}T\d{6})")
CACHE_DATE_FMT = "%Y-%m-%dT%H:%M:%S"


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(p):
    """Chemin absolu, relatif a la racine du projet si necessaire."""
    p = Path(p).expanduser()
    return p if p.is_absolute() else ROOT / p


# ------------------------------------------------------------------
# Fichiers locaux
# ------------------------------------------------------------------

def list_nc_files(swot_dir, filter_resolution=None):
    """Liste recursive des .nc, memes filtres de nom que la toolbox.

    Les fichiers commencant par « ._ » sont des AppleDouble : macOS les
    cree en copiant vers un volume exFAT/FAT. Ils portent le nom d'un
    granule mais ne contiennent que des metadonnees, d'ou des erreurs
    « Unknown file format » a la lecture.
    """
    out = []
    for root, dirs, files in os.walk(swot_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d != "__MACOSX"]
        for f in files:
            if not f.endswith(".nc") or f.startswith("._") or f.startswith("."):
                continue
            if filter_resolution and str(filter_resolution) not in f:
                continue
            out.append(os.path.join(root, f))
    return sorted(out)


def granule_datetime(name):
    """Date d'acquisition extraite du nom de fichier, ou None."""
    m = GRANULE_DATE_RE.search(os.path.basename(name))
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S") if m else None


def newest_granule_datetime(files):
    dates = [d for d in (granule_datetime(f) for f in files) if d]
    return max(dates) if dates else None


def compute_since_date(files, lookback_days, start_date):
    """Borne basse de recherche : dernier granule local - marge,
    ou start_date si le repertoire est vide."""
    newest = newest_granule_datetime(files)
    if newest is None:
        return datetime.strptime(start_date, "%Y-%m-%d")
    return newest - timedelta(days=lookback_days)


# ------------------------------------------------------------------
# Telechargement incremental (earthaccess)
# ------------------------------------------------------------------

def _earthdata_login(earthaccess):
    """Login Earthdata : interactif en terminal, sinon ~/.netrc ou
    variables d'environnement. Aucun identifiant dans ce depot."""
    if sys.stdin and sys.stdin.isatty():
        auth = earthaccess.login(persist=True)
        if auth and getattr(auth, "authenticated", False):
            return auth
    else:
        for strategy in ("environment", "netrc"):
            try:
                auth = earthaccess.login(strategy=strategy)
            except Exception:
                continue
            if auth and getattr(auth, "authenticated", False):
                return auth
    raise RuntimeError(
        "Identifiants Earthdata indisponibles : executez une fois "
        "`python pipeline/update_swot.py --download` dans un terminal "
        "(login interactif, memorise dans ~/.netrc)."
    )


def get_collections(dl):
    """Normalise la config : short_names (liste) ou short_name (chaine)."""
    names = dl.get("short_names") or dl.get("short_name")
    if names is None:
        raise ValueError("config download: short_names (ou short_name) manquant.")
    return [names] if isinstance(names, str) else list(names)


def granule_nc_basenames(granule):
    """Noms des fichiers .nc d'un granule distant."""
    try:
        links = granule.data_links()
    except Exception:
        links = []
    return {l.split("/")[-1] for l in links if l.endswith(".nc")}


def newest_remote_datetime(granules):
    """Date d'acquisition la plus recente parmi des granules distants
    (extraite des noms de fichiers)."""
    dates = []
    for g in granules:
        for name in granule_nc_basenames(g):
            d = granule_datetime(name)
            if d:
                dates.append(d)
    return max(dates) if dates else None


def filter_new_granules(granules, local_basenames):
    """Granules dont au moins un fichier .nc n'est pas deja sur disque."""
    fresh = []
    for g in granules:
        names = granule_nc_basenames(g)
        if names and not names.issubset(local_basenames):
            fresh.append(g)
    return fresh


def download_new_granules(cfg):
    """Recherche les granules plus recents que le dernier granule local
    (dans chaque collection configuree) et ne telecharge que les
    nouveaux.

    Retourne un dict :
        downloaded               nombre de granules telecharges
        found_in_window          granules trouves sur la fenetre (toutes
                                 collections et motifs confondus)
        last_remote_granule_date date du granule distant le plus recent
    """
    try:
        import earthaccess
    except ImportError:
        raise RuntimeError("earthaccess n'est pas installe (pip install earthaccess).")

    dl = cfg["download"]
    collections = get_collections(dl)
    target = resolve_path(dl["target_dir"])
    target.mkdir(parents=True, exist_ok=True)
    swot_dir = resolve_path(cfg["paths"]["swot_data"])

    all_local = list_nc_files(str(swot_dir)) if swot_dir.exists() else []
    all_local += list_nc_files(str(target)) if target != swot_dir else []
    local_basenames = {os.path.basename(f) for f in all_local}

    since = compute_since_date(
        all_local,
        dl.get("lookback_days", 45),
        dl.get("start_date")
        or cfg.get("extraction", {}).get("date_min")
        or "2023-01-01",
    )
    now = datetime.now(timezone.utc)
    temporal = (since.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d 23:59:59"))
    print(f"Recherche des granules depuis le {temporal[0]} "
          f"(dernier granule local - {dl.get('lookback_days', 45)} j)")

    _earthdata_login(earthaccess)

    total_new = 0
    total_found = 0
    newest_remote = None

    for collection in collections:
        print(f"\nCollection {collection} :")
        for pattern in dl["granule_patterns"]:
            results = earthaccess.search_data(
                short_name=collection,
                granule_name=pattern,
                temporal=temporal,
            )
            total_found += len(results)
            remote = newest_remote_datetime(results)
            if remote and (newest_remote is None or remote > newest_remote):
                newest_remote = remote
            fresh = filter_new_granules(results, local_basenames)
            print(f"  {pattern}: {len(results)} granules sur la fenetre"
                  + (f" (plus recent : {remote.strftime('%Y-%m-%d')})" if remote else "")
                  + f", {len(fresh)} nouveaux")
            if fresh:
                earthaccess.download(fresh, str(target))
                total_new += len(fresh)
                local_basenames |= {n for g in fresh
                                    for n in granule_nc_basenames(g)}

    if total_found == 0:
        print("Attention : aucun granule trouve sur la fenetre, toutes "
              "collections confondues — verifier short_names et "
              "granule_patterns dans config.yaml.")
    print(f"Telechargement termine : {total_new} nouveau(x) granule(s).")

    return {
        "downloaded": total_new,
        "found_in_window": total_found,
        "last_remote_granule_date":
            newest_remote.strftime(CACHE_DATE_FMT) if newest_remote else None,
    }


# ------------------------------------------------------------------
# Cache d'extraction
# ------------------------------------------------------------------

def load_cache(path):
    if Path(path).exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("Cache illisible : il sera reconstruit.")
    return {}


def save_cache(path, cache):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def site_key(site):
    """Cle de cache d'un site.

    Fondee sur les COORDONNEES seules : le nom est une etiquette, la
    position est l'identite. Renommer un site (corriger « Belt Bay »
    en « Madigan Gulf », par exemple) ne doit pas obliger a reprocesser
    des centaines de granules.
    """
    return f"@{site['lon']:.6f},{site['lat']:.6f}"


def legacy_site_key(site):
    """Ancienne cle, incluant le nom — pour reprendre un cache existant."""
    return f"{site['name']}@{site['lon']},{site['lat']}"


def site_fingerprint(site, ex):
    qual = ex.get("wse_qual_filter")
    return {
        "lon": site["lon"],
        "lat": site["lat"],
        "buffer_size": ex.get("buffer_size", 0),
        "wse_qual_filter": list(qual) if qual is not None else None,
    }


# ------------------------------------------------------------------
# Filtres aval — copie fidele de extract_wse_timeseries_parallel
# (SWOT_toolbox.SWOT_tools) : bornes [-16, 6] puis outliers IQR,
# par groupe (pass, resolution, tile), groupes actifs si n >= 4.
# ------------------------------------------------------------------

def apply_post_filters(df, filter_bound, filter_outliers):
    import pandas as pd

    if df.empty:
        return df
    df = df.sort_values(by="date")

    if filter_bound:
        filtered = []
        for _, group in df.groupby(["pass", "resolution", "tile"]):
            if len(group) >= 4:
                group = group[(group["wse"] >= -16) & (group["wse"] <= 6)]
            filtered.append(group)
        df = pd.concat(filtered).sort_values(by="date")

    if filter_outliers and len(df) > 3:
        filtered = []
        for _, group in df.groupby(["pass", "resolution", "tile"]):
            if len(group) >= 4:
                q1 = group["wse"].quantile(0.25)
                q3 = group["wse"].quantile(0.75)
                iqr = q3 - q1
                group = group[(group["wse"] >= q1 - 1.5 * iqr)
                              & (group["wse"] <= q3 + 1.5 * iqr)]
            filtered.append(group)
        df = pd.concat(filtered).sort_values(by="date")

    return df


# ------------------------------------------------------------------
# Extraction incrementale (worker _process_file de la toolbox)
# ------------------------------------------------------------------

def extract_sites_incremental(cfg, rebuild=False):
    """Ne traite que les fichiers absents du cache (ou modifies),
    puis reassemble et filtre chaque serie complete.

    Retourne (sites_out, source_info).
    """
    from SWOT_toolbox.SWOT_tools import _process_file
    import pandas as pd

    ex = cfg["extraction"]
    swot_dir = resolve_path(cfg["paths"]["swot_data"])
    if not swot_dir.exists():
        raise ValueError(f"Directory '{swot_dir}' does not exist.")

    files = list_nc_files(str(swot_dir), ex.get("filter_resolution"))
    cache_path = resolve_path(cfg["paths"].get("cache", "data/extraction_cache.json"))
    cache = {} if rebuild else load_cache(cache_path)
    cache.setdefault("sites", {})

    qual = ex.get("wse_qual_filter")
    qual = list(qual) if qual is not None else None
    n_workers = ex.get("n_workers") or max(1, multiprocessing.cpu_count() - 1)

    new_files_union = set()
    sites_out = []

    for site in cfg["sites"]:
        key = site_key(site)
        fp = site_fingerprint(site, ex)
        entry = cache["sites"].get(key)
        if entry is None:
            # Migration depuis l'ancienne cle (nom inclus) : evite de
            # tout reprocesser apres un simple renommage.
            legacy = cache["sites"].pop(legacy_site_key(site), None)
            if legacy is not None:
                entry = legacy
                print(f"  cache repris de l'ancienne clé "
                      f"({legacy_site_key(site)})")
        if not entry or entry.get("fingerprint") != fp:
            entry = {"fingerprint": fp, "files": {}}
        known = entry["files"]

        todo = []
        for path in files:
            b = os.path.basename(path)
            rec = known.get(b)
            if rec is None or rec.get("size") != os.path.getsize(path):
                todo.append(path)

        print(f"\n=== {site['name']} ({site['lon']}, {site['lat']}) — "
              f"{len(files)} granules, {len(todo)} a traiter ===")

        if todo:
            new_files_union.update(os.path.basename(p) for p in todo)
            process = partial(_process_file, lon=site["lon"], lat=site["lat"],
                              buffer_size=ex.get("buffer_size", 0),
                              wse_qual_filter=qual, debug=False)

            def store(path, res):
                known[os.path.basename(path)] = {
                    "size": os.path.getsize(path),
                    "date": res["date"].strftime(CACHE_DATE_FMT) if res else None,
                    "wse": float(res["wse"]) if res else None,
                }

            done = 0
            if n_workers <= 1:
                # Sequentiel : pratique pour deboguer (tracebacks directs)
                for path in todo:
                    store(path, process(path))
                    done += 1
                    if done % 20 == 0 or done == len(todo):
                        print(f"  {done}/{len(todo)} fichiers traites")
            else:
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    futures = {executor.submit(process, p): p for p in todo}
                    for future in as_completed(futures):
                        store(futures[future], future.result())
                        done += 1
                        if done % 20 == 0 or done == len(todo):
                            print(f"  {done}/{len(todo)} fichiers traites")

        cache["sites"][key] = entry

        # Reassemblage de la serie complete depuis le cache
        # (uniquement les fichiers actuellement presents sur disque)
        rows = []
        for path in files:
            rec = known.get(os.path.basename(path))
            if rec and rec.get("wse") is not None:
                rows.append({
                    "date": datetime.strptime(rec["date"], CACHE_DATE_FMT),
                    "wse": rec["wse"], "filename": path,
                    "pass": "Unknown", "resolution": "Unknown", "tile": "Unknown",
                })
        df = pd.DataFrame(rows, columns=["date", "wse", "filename",
                                         "pass", "resolution", "tile"])
        df = apply_post_filters(df, ex.get("filter_bound", False),
                                ex.get("filter_outliers", False))

        records = dataframe_to_records(
            df, date_min=ex.get("date_min"), date_max=ex.get("date_max"),
            datum_offset=site.get("datum_offset", 0.0),
        )
        sites_out.append(build_site_entry(site, records))

    save_cache(cache_path, cache)

    newest = newest_granule_datetime(files)
    source = {
        "n_granules": len(files),
        "last_granule_date": newest.strftime(CACHE_DATE_FMT) if newest else None,
        "new_this_run": len(new_files_union),
    }
    return sites_out, source


# ------------------------------------------------------------------
# Extraction d'origine (verification croisee, sans cache)
# ------------------------------------------------------------------

def extract_sites(cfg):
    """Chemin d'origine : extract_wse_timeseries_parallel de la toolbox,
    telle quelle, sur l'ensemble du repertoire."""
    from SWOT_toolbox import SWOT_tools as stools

    ex = cfg["extraction"]
    swot_dir = str(resolve_path(cfg["paths"]["swot_data"]))

    sites_out = []
    for site in cfg["sites"]:
        print(f"\n=== {site['name']} ({site['lon']}, {site['lat']}) ===")
        df = stools.extract_wse_timeseries_parallel(
            directory_path=swot_dir,
            lon=site["lon"],
            lat=site["lat"],
            buffer_size=ex.get("buffer_size", 0),
            filter_resolution=ex.get("filter_resolution"),
            filter_outliers=ex.get("filter_outliers", False),
            filter_bound=ex.get("filter_bound", False),
            wse_qual_filter=list(ex["wse_qual_filter"])
            if ex.get("wse_qual_filter") is not None
            else None,
        )
        records = dataframe_to_records(
            df, date_min=ex.get("date_min"), date_max=ex.get("date_max"),
            datum_offset=site.get("datum_offset", 0.0),
        )
        sites_out.append(build_site_entry(site, records))
    return sites_out


# ------------------------------------------------------------------
# Mise en forme des series
# ------------------------------------------------------------------

def dataframe_to_records(df, date_min=None, date_max=None, datum_offset=0.0):
    """DataFrame (date, wse) -> liste triee de {date, wse} serialisable.
    Applique la fenetre temporelle et le decalage de datum du site."""
    if df is None or len(df) == 0:
        return []

    df = df.copy()
    if date_min:
        df = df[df["date"] >= date_min]
    if date_max:
        df = df[df["date"] <= date_max]
    df = df.sort_values("date")

    records = []
    for _, row in df.iterrows():
        d = row["date"]
        iso = d.strftime(CACHE_DATE_FMT) if hasattr(d, "strftime") else str(d)
        records.append({"date": iso, "wse": round(float(row["wse"]) + datum_offset, 3)})
    return records


def build_site_entry(site, records):
    entry = {
        "name": site["name"],
        "lon": site["lon"],
        "lat": site["lat"],
        "datum_offset": site.get("datum_offset", 0.0),
        "series": records,
        "latest": None,
        "stats": None,
    }
    if records:
        values = [r["wse"] for r in records]
        entry["latest"] = records[-1]
        entry["stats"] = {
            "n": len(records),
            "min": min(values),
            "max": max(values),
            "first_date": records[0]["date"],
            "last_date": records[-1]["date"],
        }
    return entry


# ------------------------------------------------------------------
# Mode demonstration
# ------------------------------------------------------------------

def make_demo_sites(cfg):
    """Series synthetiques (clairement etiquetees) : crue puis recession
    lente, pas irregulier ~10 j."""
    rng = random.Random(42)
    sites_out = []
    for k, site in enumerate(cfg["sites"]):
        records = []
        t = datetime(2025, 2, 1)
        end = datetime.now()
        base_floor = -15.4 + 0.15 * k
        peak = -11.8 + 0.1 * k
        peak_day = datetime(2025, 6, 15)
        while t <= end:
            days = (t - peak_day).days
            if days < 0:
                frac = max(0.0, 1 + days / 134.0)
                wse = base_floor + (peak - base_floor) * frac
            else:
                wse = base_floor + (peak - base_floor) * math.exp(-days / 420.0)
            wse += rng.gauss(0, 0.06)
            records.append(
                {"date": t.strftime(CACHE_DATE_FMT), "wse": round(wse, 3)}
            )
            t += timedelta(days=rng.randint(7, 14))
        sites_out.append(build_site_entry(site, records))
    return sites_out


# ------------------------------------------------------------------
# Ecriture du JSON
# ------------------------------------------------------------------

def write_payload(cfg, sites_out, demo, output=None, source=None):
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo": bool(demo),
        "lake": cfg["lake"],
        "datum_label": cfg.get("display", {}).get("datum_label", "WSE (m)"),
        "source": source,
        "sites": sites_out,
    }

    out_path = resolve_path(output or cfg["paths"]["output_json"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    n_obs = sum(len(s["series"]) for s in sites_out)
    print(f"\nJSON ecrit : {out_path} ({len(sites_out)} sites, {n_obs} observations)")
    if source and source.get("last_granule_date"):
        print(f"  Dernier granule local : {source['last_granule_date']} "
              f"({source['n_granules']} granules, "
              f"{source['new_this_run']} traites a cette execution)")
    for s in sites_out:
        if s["latest"]:
            print(f"  {s['name']}: derniere WSE = {s['latest']['wse']} m "
                  f"le {s['latest']['date']}")
        else:
            print(f"  {s['name']}: aucune donnee")
    return out_path


# ------------------------------------------------------------------
# Point d'entree
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pipeline SWOT -> JSON")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--output", default=None,
                        help="Fichier JSON de sortie (defaut: config)")
    parser.add_argument("--download", action="store_true",
                        help="Recherche et telecharge les nouveaux granules")
    parser.add_argument("--demo", action="store_true",
                        help="Genere des donnees synthetiques de demonstration")
    parser.add_argument("--rebuild-cache", action="store_true",
                        help="Ignore le cache et retraite tous les fichiers")
    parser.add_argument("--no-cache", action="store_true",
                        help="Utilise extract_wse_timeseries_parallel d'origine")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.demo:
        sites_out = make_demo_sites(cfg)
        write_payload(cfg, sites_out, demo=True, output=args.output)
        return

    downloaded = download_new_granules(cfg) if args.download else None

    if args.no_cache:
        sites_out = extract_sites(cfg)
        files = list_nc_files(str(resolve_path(cfg["paths"]["swot_data"])),
                              cfg["extraction"].get("filter_resolution"))
        newest = newest_granule_datetime(files)
        source = {
            "n_granules": len(files),
            "last_granule_date": newest.strftime(CACHE_DATE_FMT) if newest else None,
            "new_this_run": (downloaded or {}).get("downloaded", 0),
        }
    else:
        sites_out, source = extract_sites_incremental(cfg, rebuild=args.rebuild_cache)

    if downloaded is not None:
        source["downloaded"] = downloaded["downloaded"]
        source["found_in_window"] = downloaded["found_in_window"]
        source["last_remote_granule_date"] = downloaded["last_remote_granule_date"]

    write_payload(cfg, sites_out, demo=False, output=args.output, source=source)


if __name__ == "__main__":
    main()
