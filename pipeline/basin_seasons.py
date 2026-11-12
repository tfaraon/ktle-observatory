#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pluie saisonniere sur le bassin du lac Eyre, de 1900 a aujourd'hui.

    python pipeline/basin_seasons.py              # reprend le cache, complete
    python pipeline/basin_seasons.py --first 1950
    python pipeline/basin_seasons.py --demo       # serie synthetique, sans reseau

Le contexte climatique d'une crue demande un siecle, pas un mois : cette
page-ci agrege les grilles *mensuelles* SILO (0,05 degre, CC BY 4.0) en
deux saisons par annee. La page jour par jour, elle, vit dans
fetch_rainfall.py et ne garde que les dernieres semaines.

Saisons, pour un bassin ou la pluie vient de la mousson du nord-est :
  - chaude : octobre a mars, a cheval sur deux annees civiles ;
  - fraiche : avril a septembre.
L'annee d'une saison chaude est celle de son mois d'octobre : la saison
chaude 1974 va d'octobre 1974 a mars 1975. Les deux dernieres annees
sont donc incompletes une partie de l'annee, et le JSON le dit.

Cout. Une grille mensuelle fait quelques centaines de kilo-octets et
n'est gardee que le temps d'en tirer une moyenne : seul le cache des
moyennes reste, un nombre par mois, environ 60 ko pour 125 ans. Il est
versionne, pour que le premier passage long se fasse une fois sur une
machine et que la forge n'ait plus ensuite que les mois nouveaux a
chercher. Le cache est ecrit apres chaque annee : une coupure ne fait
pas tout recommencer.

Precaution affichee sur le site : avant 1950 les pluviometres du bassin
se comptent sur les doigts, et SILO interpole. Les premieres decennies
donnent un ordre de grandeur, pas une mesure.
"""

import argparse
import hashlib
import json
import math
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import yaml

import basin_outline as bo
from fetch_rainfall import read_geotiff

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_FILE = DATA / "basin_seasons.json"
CACHE_FILE = DATA / "season_cache.json"
TMP_DIR = DATA / "season_tmp"

BASE = "https://s3-ap-southeast-2.amazonaws.com/silo-open-data/Official"
MONTHLY_URL = BASE + "/monthly/monthly_rain/{y}/{y}{m:02d}.monthly_rain.tif"
DAILY_URL = BASE + "/daily/daily_rain/{y}/{y}{m:02d}{d:02d}.daily_rain.tif"
USER_AGENT = ("ktle-observatory/1.0 (research outreach; "
              "github.com/tfaraon/ktle-observatory)")

WARM = (10, 11, 12, 1, 2, 3)
COOL = (4, 5, 6, 7, 8, 9)
SILO_FIRST_YEAR = 1889
SPARSE_BEFORE = 1950          # avant cette date, tres peu de pluviometres

DEFAULTS = {"first": 1900, "revisit_months": 2}


def settings(cfg):
    s = dict(DEFAULTS, **((cfg or {}).get("seasons") or {}))
    s["first"] = max(SILO_FIRST_YEAR, int(s["first"]))
    s["revisit_months"] = max(0, min(int(s["revisit_months"]), 12))
    return s


# ── Cache ───────────────────────────────────────────────────────
#
# Une moyenne sur le bassin n'a de sens qu'avec le masque qui l'a
# produite. Changer de contour (le GeoJSON officiel a la place du
# contour simplifie) deplace la moyenne de plusieurs pour cent : des
# mois calcules sur deux masques differents ne se comparent plus. Le
# cache porte donc l'empreinte du contour, et se vide s'il change.

def outline_digest(outline):
    pts = ";".join(f"{x:.4f},{y:.4f}" for x, y in outline)
    return hashlib.sha256(pts.encode("ascii")).hexdigest()[:16]


def load_cache(digest):
    if not CACHE_FILE.exists():
        return {}, None
    try:
        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}, "cache illisible"
    if raw.get("outline") != digest:
        return {}, ("le contour du bassin a change : les moyennes en cache "
                    "ne sont plus comparables, elles sont recalculees")
    months = {k: v for k, v in (raw.get("months") or {}).items()
              if isinstance(v, (int, float))}
    return months, None


def save_cache(months, digest, kind, cells):
    CACHE_FILE.write_text(json.dumps({
        "outline": digest,
        "outline_kind": kind,
        "cells": int(cells),
        "note": ("Moyenne de pluie mensuelle sur le bassin, en mm, "
                 "ponderee par le cosinus de la latitude. Produit par "
                 "pipeline/basin_seasons.py ; ne pas editer a la main."),
        "months": {k: round(float(v), 4) for k, v in sorted(months.items())},
    }, indent=0), encoding="utf-8")


# ── Telechargement ──────────────────────────────────────────────

def download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        f.write(r.read())


def monthly_available(year=2000, month=6, timeout=30):
    """Les grilles mensuelles existent-elles la ou on les attend ?

    Verifie avant d'ouvrir un siecle de telechargements, pour echouer
    sur un message clair plutot qu'au bout de la premiere annee.
    """
    url = MONTHLY_URL.format(y=year, m=month)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                 method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200, url
    except Exception as e:                      # reseau, 403, 404
        return False, f"{url} ({type(e).__name__})"


# ── Moyenne sur le bassin ───────────────────────────────────────

def weights(lats, mask):
    """Ponderation par le cosinus de la latitude.

    Une maille de 0,05 degre couvre moins de sol vers le sud : sur
    l'etendue du bassin l'ecart atteint 8 %, ce qui n'est pas rien dans
    une moyenne qu'on compare d'une decennie a l'autre.
    """
    w = np.cos(np.deg2rad(np.asarray(lats, float)))[:, None]
    return np.broadcast_to(w, mask.shape) * mask


def grid_mean(path, outline, cached_mask=None):
    """Moyenne sur le bassin d'une grille, et le masque pour la suivante."""
    g, lons, lats = read_geotiff(path)
    mask, w = cached_mask if cached_mask else (None, None)
    if mask is None or mask.shape != g.shape:
        mask = bo.grid_mask(outline, lons, lats)
        w = weights(lats, mask)
    ok = mask & np.isfinite(g)
    if not ok.any():
        raise ValueError("aucune maille du bassin dans cette grille")
    total = float((np.where(ok, w, 0.0) * np.nan_to_num(g)).sum())
    return total / float(np.where(ok, w, 0.0).sum()), (mask, w)


def month_mean(year, month, outline, cache_mask, from_daily=False):
    """Pluie moyenne sur le bassin pour un mois, en mm."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if not from_daily:
        dest = TMP_DIR / f"{year}{month:02d}.tif"
        try:
            download(MONTHLY_URL.format(y=year, m=month), dest)
            return grid_mean(dest, outline, cache_mask)
        finally:
            dest.unlink(missing_ok=True)
    # Repli : somme des grilles quotidiennes. Trente fois plus de
    # fichiers, donc jamais automatique.
    days = (date(year + (month == 12), month % 12 + 1, 1)
            - date(year, month, 1)).days
    total, mask = None, cache_mask
    for d in range(1, days + 1):
        dest = TMP_DIR / f"{year}{month:02d}{d:02d}.tif"
        try:
            download(DAILY_URL.format(y=year, m=month, d=d), dest)
            m, mask = grid_mean(dest, outline, mask)
            total = m if total is None else total + m
        finally:
            dest.unlink(missing_ok=True)
    if total is None:
        raise ValueError("aucun jour disponible")
    return total, mask


# ── Agregation en saisons ───────────────────────────────────────

def season_months(year, season):
    """Les (annee, mois) d'une saison. La saison chaude mord sur l'an d'apres."""
    if season == "cool":
        return [(year, m) for m in COOL]
    return [(year, m) for m in (10, 11, 12)] + [(year + 1, m) for m in (1, 2, 3)]


def aggregate(months, first, last):
    """Une ligne par annee : les deux saisons, et ce qui manque."""
    rows = []
    for y in range(first, last + 1):
        row = {"year": y}
        for name in ("warm", "cool"):
            want = season_months(y, name)
            have = [months[f"{yy}{mm:02d}"] for yy, mm in want
                    if f"{yy}{mm:02d}" in months]
            row[name + "_mm"] = round(sum(have), 1) if have else None
            row[name + "_months"] = len(have)
        if row["warm_mm"] is not None and row["cool_mm"] is not None:
            row["total_mm"] = round(row["warm_mm"] + row["cool_mm"], 1)
        else:
            row["total_mm"] = None
        row["complete"] = row["warm_months"] == 6 and row["cool_months"] == 6
        rows.append(row)
    while rows and rows[-1]["warm_months"] == 0 and rows[-1]["cool_months"] == 0:
        rows.pop()
    return rows


def norms(rows, first=None, last=None):
    """Moyennes de longue periode, sur les seules annees completes."""
    use = [r for r in rows if r["complete"]
           and (first is None or r["year"] >= first)
           and (last is None or r["year"] <= last)]
    out = {"years": len(use),
           "from": use[0]["year"] if use else None,
           "to": use[-1]["year"] if use else None}
    for k in ("warm_mm", "cool_mm", "total_mm"):
        vals = [r[k] for r in use if r[k] is not None]
        out[k] = round(sum(vals) / len(vals), 1) if vals else None
    if out["total_mm"] and out["warm_mm"] is not None:
        out["warm_share"] = round(100.0 * out["warm_mm"] / out["total_mm"])
    return out


def rank_of(rows, year):
    """Rang d'une annee parmi les annees completes, de la plus humide."""
    use = sorted((r for r in rows if r["complete"] and r["total_mm"] is not None),
                 key=lambda r: -r["total_mm"])
    for i, r in enumerate(use, 1):
        if r["year"] == year:
            return {"rank": i, "of": len(use)}
    return None


# ── Passage complet ─────────────────────────────────────────────

def run(cfg=None, first=None, last=None, demo=False, from_daily=False,
        quiet=False, write=True):
    cfg = cfg if cfg is not None else read_config()
    s = settings(cfg)
    first = int(first or s["first"])
    today = date.today()
    last = int(last if last is not None else today.year)
    outline, kind = bo.load_outline(cfg)
    digest = outline_digest(outline)

    if demo:
        months, warnings, cells = demo_months(first, last, today), [], 0
    else:
        months, reset = load_cache(digest)
        warnings = [reset] if reset else []
        ok, where = monthly_available()
        if not ok and not from_daily:
            raise RuntimeError(
                "Les grilles mensuelles SILO ne repondent pas : " + str(where)
                + "\nSi l'adresse a change, corriger MONTHLY_URL. Pour passer "
                  "par les grilles quotidiennes (trente fois plus de "
                  "fichiers), relancer avec --from-daily.")
        # Les derniers mois peuvent etre revises par SILO : on les reprend.
        for k in recent_keys(today, s["revisit_months"]):
            months.pop(k, None)
        months, cells, errs = fill(months, first, last, outline, today,
                                   from_daily=from_daily, quiet=quiet,
                                   digest=digest, kind=kind)
        warnings += errs
        save_cache(months, digest, kind, cells)

    rows = aggregate(months, first, last)
    done = [r for r in rows if r["complete"]]
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "SILO monthly rainfall grids, Queensland Government, CC BY 4.0",
        "licence": "CC BY 4.0",
        "url": "https://www.longpaddock.qld.gov.au/silo/",
        "basin": {"outline": kind, "cells": int(cells),
                  "weighting": "cosine of latitude"},
        "seasons": {
            "warm": {"months": list(WARM),
                     "label": "Warm season (Oct-Mar)",
                     "note": "Labelled by the year of its October."},
            "cool": {"months": list(COOL), "label": "Cool season (Apr-Sep)"},
        },
        "period": {"first": first, "last": rows[-1]["year"] if rows else first},
        "sparse_before": SPARSE_BEFORE,
        "norms": norms(rows),
        "norms_recent": norms(rows, first=1991),
        "latest": (done[-1] if done else None),
        "latest_rank": rank_of(rows, done[-1]["year"]) if done else None,
        "series": rows,
        "warnings": warnings,
    }
    if demo:
        payload["demo"] = True
    if write:
        OUT_FILE.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    if not quiet:
        report(payload)
    return payload


def recent_keys(today, n):
    keys, y, m = [], today.year, today.month
    for _ in range(n + 1):
        keys.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return keys


def fill(months, first, last, outline, today, from_daily, quiet, digest, kind):
    """Complete les mois manquants, du plus recent au plus ancien."""
    mask, cells, errs = None, 0, []
    wanted = [(y, m) for y in range(first, last + 1) for m in range(1, 13)
              if (y, m) <= (today.year, today.month)]
    todo = [(y, m) for y, m in wanted if f"{y}{m:02d}" not in months]
    if not quiet and todo:
        print(f"{len(todo)} mois a chercher ({todo[0][0]} a {todo[-1][0]})")
    for i, (y, m) in enumerate(reversed(todo), 1):
        try:
            value, mask = month_mean(y, m, outline, mask, from_daily)
        except urllib.error.HTTPError as e:
            if e.code == 404:                   # mois pas encore publie
                continue
            errs.append(f"{y}-{m:02d}: HTTP {e.code}")
            continue
        except Exception as e:
            errs.append(f"{y}-{m:02d}: {type(e).__name__}")
            continue
        months[f"{y}{m:02d}"] = value
        if mask is not None:
            cells = int(mask[0].sum())
        if m == 1 or i == len(todo):            # une sauvegarde par annee
            save_cache(months, digest, kind, cells)
            if not quiet:
                print(f"  {y} ... {i}/{len(todo)} mois", flush=True)
    if len(errs) > 12:
        errs = errs[:12] + [f"... et {len(errs) - 12} autres mois manquants"]
    return months, cells, errs


def demo_months(first, last, today):
    """Serie synthetique : une mousson nette, une variabilite forte.

    Sert a developper la page sans reseau. Marquee « demo » dans le JSON
    pour qu'elle ne puisse pas passer pour une mesure.
    """
    rng = np.random.default_rng(1974)
    out = {}
    for y in range(first, last + 1):
        for m in range(1, 13):
            if (y, m) > (today.year, today.month):
                break
            warm = m in WARM
            base = 22.0 if warm else 9.0
            # Loi log-normale : des mois secs nombreux, quelques deluges
            v = float(rng.lognormal(math.log(base) - 0.5, 1.0))
            out[f"{y}{m:02d}"] = round(min(v, 320.0), 3)
    return out


def read_config():
    p = ROOT / "config.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def report(p):
    n = p["norms"]
    print(f"{OUT_FILE.relative_to(ROOT)} : {len(p['series'])} annees, "
          f"{p['period']['first']}-{p['period']['last']}"
          + (" (DEMO)" if p.get("demo") else ""))
    if n["total_mm"]:
        print(f"  moyenne {n['from']}-{n['to']} : {n['total_mm']} mm/an, "
              f"dont {n.get('warm_share')} % en saison chaude")
    if p["latest"]:
        r, lt = p["latest_rank"], p["latest"]
        print(f"  derniere annee complete {lt['year']} : {lt['total_mm']} mm"
              + (f", {r['rank']}e sur {r['of']}" if r else ""))
    for w in p["warnings"]:
        print("  ! " + str(w))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--first", type=int, help="premiere annee (defaut : config)")
    ap.add_argument("--last", type=int, help="derniere annee")
    ap.add_argument("--demo", action="store_true",
                    help="serie synthetique, sans reseau")
    ap.add_argument("--from-daily", action="store_true",
                    help="sommer les grilles quotidiennes (trente fois plus "
                         "de fichiers)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    run(first=a.first, last=a.last, demo=a.demo, from_daily=a.from_daily,
        quiet=a.quiet)


if __name__ == "__main__":
    main()
