#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Observations d'oiseaux recentes autour de Kati Thanda, via l'API eBird 2.0.

    EBIRD_API_KEY=... python pipeline/fetch_ebird.py
    python pipeline/fetch_ebird.py --demo

La cle est personnelle (gratuite sur https://ebird.org/api/keygen). Elle
est lue dans la variable d'environnement EBIRD_API_KEY, jamais dans
config.yaml ni dans le depot, et jamais ecrite dans le fichier produit.
Un site statique qui interrogerait eBird depuis le navigateur l'exposerait
a tous : la recuperation se fait donc cote serveur, comme pour le BOM.

Conditions d'utilisation d'eBird : usage non commercial libre ; eBird.org
doit etre cite comme source partout ou ses donnees s'affichent, avec un
lien. Le fichier ne conserve que les champs utiles a l'affichage, sans
nom d'observateur, et les coordonnees des lieux prives sont retirees.

Les points d'acces « recent » ne renvoient que la derniere observation
de chaque espece : le resultat est une liste d'especes vues sur la
periode, pas un recensement.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EBIRD_FILE = ROOT / "data" / "ebird.json"
API = "https://api.ebird.org/v2"

ATTRIBUTION = ("Bird observations from eBird.org, Cornell Lab of Ornithology. "
               "Records are submitted by volunteer observers.")
ATTRIBUTION_URL = "https://ebird.org"

# Champs conserves : strictement ce qu'affiche le site
KEEP = ("speciesCode", "comName", "sciName", "howMany", "obsDt",
        "locId", "locName", "lat", "lng", "obsValid", "obsReviewed",
        "locationPrivate")

DEFAULTS = {
    "back_days": 30,
    "dist_km": 50,
    "points": [
        {"name": "Lake Eyre North", "lat": -28.20, "lon": 137.30},
        {"name": "Belt Bay", "lat": -28.89, "lon": 137.03},
        {"name": "Madigan Gulf", "lat": -28.89, "lon": 137.56},
        {"name": "Lake Eyre South", "lat": -29.25, "lon": 137.30},
    ],
    # Oiseaux d'eau dont la presence signale un lac en eau, reconnus
    # par nom scientifique (les codes eBird sont moins stables).
    "indicator_species": [
        "Cladorhynchus leucocephalus",     # banded stilt
        "Pelecanus conspicillatus",        # Australian pelican
        "Recurvirostra novaehollandiae",   # red-necked avocet
        "Chroicocephalus novaehollandiae", # silver gull
        "Gelochelidon macrotarsa",         # Australian tern
    ],
}


def api_get(path, params, key, timeout=20):
    """Requete eBird ; la cle voyage dans l'en-tete, jamais dans l'URL."""
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "x-ebirdapitoken": key,
        "User-Agent": "ktle-observatory (research, non-commercial)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def slim(obs):
    """Observation reduite aux champs affiches.

    Un lieu prive (propriete, station pastorale) garde son espece mais
    perd son nom et ses coordonnees : rien ne justifie de publier
    l'emplacement exact d'un lieu que son observateur a voulu prive.
    """
    rec = {k: obs.get(k) for k in KEEP}
    if rec.get("locationPrivate"):
        rec["locName"] = None
        rec["lat"] = rec["lng"] = None
        rec["locId"] = None
    return rec


def obs_time(rec):
    try:
        return datetime.strptime(rec.get("obsDt") or "", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            return datetime.strptime(rec.get("obsDt") or "", "%Y-%m-%d")
        except ValueError:
            return datetime.min


def merge_species(batches):
    """Une entree par espece : la plus recente, tous points confondus.

    Les cercles de recherche se recouvrent, une meme espece remonte donc
    de plusieurs points ; seule sa derniere observation est gardee.
    """
    best = {}
    for batch in batches:
        for obs in batch:
            code = obs.get("speciesCode")
            if not code:
                continue
            rec = slim(obs)
            if code not in best or obs_time(rec) > obs_time(best[code]):
                best[code] = rec
    return sorted(best.values(), key=obs_time, reverse=True)


def annotate(species, notable_codes, indicators):
    wanted = {s.strip().lower() for s in indicators}
    for rec in species:
        rec["notable"] = rec.get("speciesCode") in notable_codes
        rec["indicator"] = (rec.get("sciName") or "").strip().lower() in wanted
    return species


def summarise(species, indicators):
    present = {(r.get("sciName") or "").lower(): r for r in species
               if r.get("indicator")}
    return [{
        "sciName": sci,
        "comName": present[sci.lower()]["comName"] if sci.lower() in present else None,
        "present": sci.lower() in present,
        "lastSeen": present[sci.lower()]["obsDt"] if sci.lower() in present else None,
    } for sci in indicators]


def load_previous(demo=False):
    """Dernier fichier valide, s'il est de meme nature (demo ou reel).

    Meme regle que pour la meteo : des donnees de demonstration ne
    doivent jamais passer pour des observations reelles, ni l'inverse.
    """
    if not EBIRD_FILE.exists():
        return None
    try:
        with open(EBIRD_FILE, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        return None
    return prev if bool(prev.get("demo")) == bool(demo) else None


def make_demo(ecfg):
    now = datetime.now(timezone.utc)
    pool = [
        ("bansti1", "Banded Stilt", "Cladorhynchus leucocephalus", 1200),
        ("auspel1", "Australian Pelican", "Pelecanus conspicillatus", 340),
        ("renavo1", "Red-necked Avocet", "Recurvirostra novaehollandiae", 85),
        ("silgul1", "Silver Gull", "Chroicocephalus novaehollandiae", 60),
        ("zebfin2", "Zebra Finch", "Taeniopygia castanotis", 12),
        ("crow1", "Little Crow", "Corvus bennetti", 4),
    ]
    out = []
    for k, (code, com, sci, n) in enumerate(pool):
        p = ecfg["points"][k % len(ecfg["points"])]
        out.append({"speciesCode": code, "comName": com, "sciName": sci,
                    "howMany": n,
                    "obsDt": (now - timedelta(days=2 * k)).strftime("%Y-%m-%d %H:%M"),
                    "locId": f"L{k}", "locName": f"{p['name']} (demonstration)",
                    "lat": p["lat"], "lng": p["lon"],
                    "obsValid": True, "obsReviewed": False,
                    "locationPrivate": False})
    return out


def update(cfg, demo=False, key=None, write=True):
    ecfg = dict(DEFAULTS, **(cfg.get("ebird") or {}))
    back = max(1, min(int(ecfg["back_days"]), 30))    # limites de l'API
    dist = max(1, min(int(ecfg["dist_km"]), 50))
    indicators = ecfg["indicator_species"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stale = False
    errors = []
    if demo:
        recent, notable = [make_demo(ecfg)], set()
    else:
        if not key:
            raise SystemExit(
                "EBIRD_API_KEY absente. Obtenez une clé gratuite sur "
                "https://ebird.org/api/keygen, puis :\n"
                "  export EBIRD_API_KEY=votre_clé\n"
                "Pour le workflow GitHub, déclarez-la comme secret du dépôt.")
        recent, notable = [], set()
        for p in ecfg["points"]:
            q = {"lat": p["lat"], "lng": p["lon"], "dist": dist, "back": back,
                 "sppLocale": "en"}
            try:
                recent.append(api_get("/data/obs/geo/recent", q, key))
                nb = api_get("/data/obs/geo/recent/notable",
                             dict(q, detail="simple"), key)
                notable.update(o.get("speciesCode") for o in nb)
            except Exception as e:
                errors.append(f"{p['name']}: {type(e).__name__}: {e}"[:160])

        if errors and not recent:
            # Aucun point n'a repondu : on garde le dernier jeu valide
            prev = load_previous(demo=False)
            if prev is None:
                raise SystemExit("eBird injoignable et aucun fichier "
                                 "précédent : " + "; ".join(errors))
            prev["stale"] = True
            prev["errors"] = errors
            if write:
                _write(prev)
            return prev

    species = annotate(merge_species(recent), notable, indicators)
    payload = {
        "fetched_at": now,
        "demo": bool(demo),
        "stale": stale,
        "partial": bool(errors),
        "errors": errors,
        "back_days": back,
        "dist_km": dist,
        "points": [{"name": p["name"], "lat": p["lat"], "lon": p["lon"]}
                   for p in ecfg["points"]],
        "n_species": len(species),
        "indicators": summarise(species, indicators),
        "species": species,
        "attribution": ATTRIBUTION,
        "attribution_url": ATTRIBUTION_URL,
    }
    if write:
        _write(payload)
    return payload


def _write(payload):
    EBIRD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EBIRD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def main():
    import os

    parser = argparse.ArgumentParser(description="Observations eBird autour du lac")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--demo", action="store_true",
                        help="Données de démonstration, sans clé ni réseau")
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    data = update(cfg, demo=args.demo, key=os.environ.get("EBIRD_API_KEY"))
    print(f"JSON écrit : {EBIRD_FILE}")
    print(f"  {data['n_species']} espèce(s) sur {data['back_days']} jours, "
          f"{len(data['points'])} point(s) de {data['dist_km']} km")
    seen = [i for i in data["indicators"] if i["present"]]
    print(f"  oiseaux d'eau indicateurs présents : {len(seen)}/{len(data['indicators'])}")
    for i in seen:
        print(f"    {i['comName']} ({i['sciName']}), vu le {i['lastSeen']}")
    if data.get("stale"):
        print("  eBird injoignable : dernier jeu valide conservé")
    elif data.get("partial"):
        print(f"  {len(data['errors'])} point(s) en erreur : {data['errors'][0]}")


if __name__ == "__main__":
    main()
