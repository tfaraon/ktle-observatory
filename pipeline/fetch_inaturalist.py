#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Observations iNaturalist autour de Kati Thanda, pour la page Observe and
share (partie Fauna and flora).

    python pipeline/fetch_inaturalist.py
    python pipeline/fetch_inaturalist.py --demo

L'API v1 d'iNaturalist est ouverte en lecture, sans cle. Ses regles :
au plus 60 requetes par minute et 10 000 par jour, et un usage tourne
vers les applications, pas l'aspiration de donnees. On fait donc trois
requetes par passage, espacees d'une seconde, une fois par jour.

Filtre : le projet iNaturalist s'il est configure (inaturalist.project),
sinon l'emprise du lac (inaturalist.bbox). Le meme filtre sert aux liens
et aux tuiles de la carte, pour que site, carte et iNaturalist montrent
les memes observations.

Licences et vie privee :
  - une photo n'est gardee que si son auteur l'a placee sous licence
    (license_code renseigne), avec l'attribution fournie par iNaturalist ;
    les photos « tous droits reserves » ne sont pas reprises ;
  - pour une observation a localisation masquee (espece menacee, choix de
    l'observateur), les coordonnees brouillees par iNaturalist ne sont pas
    conservees : on ne place pas sur la carte un point qui semblerait
    precis ;
  - seul l'identifiant public de l'observateur est garde, parce que les
    licences Creative Commons exigent de le citer.
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "inaturalist.json"
API = "https://api.inaturalist.org/v1"
WEB = "https://www.inaturalist.org"
USER_AGENT = "ktle-observatory/1.0 (research outreach; github.com/tfaraon/ktle-observatory)"

DEFAULTS = {
    "project": None,                     # identifiant du projet, une fois cree
    "place_slug": "kati-thanda-lake-eyre-national-park",
    "bbox": [136.6, -29.8, 138.3, -27.6],   # ouest, sud, est, nord
    "recent": 24,
    "top_species": 12,                   # affichees sur la page iNaturalist
    "max_species": 300,                  # toutes les especes, pour les groupes
    "pause_s": 1.0,
}


def settings(cfg):
    s = dict(DEFAULTS, **((cfg or {}).get("inaturalist") or {}))
    s["recent"] = max(1, min(int(s["recent"]), 60))
    s["top_species"] = max(1, min(int(s["top_species"]), 50))
    s["max_species"] = max(s["top_species"], min(int(s["max_species"]), 500))
    return s


def filter_params(s):
    """Filtre commun aux requetes, aux liens et aux tuiles de la carte."""
    base = {"verifiable": "true"}
    if s.get("project"):
        base["project_id"] = s["project"]
    else:
        w, south, e, n = s["bbox"]
        base.update(swlng=w, swlat=south, nelng=e, nelat=n)
    return base


def api_get(path, params, timeout=25):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def photo(p):
    """Photo reutilisable, ou None si son auteur ne l'a pas placee sous licence."""
    if not p or not p.get("license_code") or not p.get("url"):
        return None
    url = p["url"]
    return {
        "square": url,
        "medium": url.replace("/square.", "/medium."),
        "license": p["license_code"].upper(),
        "attribution": p.get("attribution") or "",
    }


def taxon_names(t):
    t = t or {}
    return {
        "name": t.get("name"),
        "common": t.get("preferred_common_name"),
        "rank": t.get("rank"),
        "group": t.get("iconic_taxon_name"),
    }


def slim_observation(o):
    obscured = bool(o.get("obscured")) or o.get("geoprivacy") in ("obscured", "private") \
        or o.get("taxon_geoprivacy") in ("obscured", "private")
    coords = None
    geo = o.get("geojson") or {}
    if not obscured and isinstance(geo.get("coordinates"), list) and len(geo["coordinates"]) == 2:
        lng, lat = geo["coordinates"]
        coords = [round(lat, 4), round(lng, 4)]
    photos = [ph for ph in (photo(p) for p in (o.get("photos") or [])) if ph]
    return {
        "id": o.get("id"),
        "url": o.get("uri") or f"{WEB}/observations/{o.get('id')}",
        "observed_on": o.get("observed_on"),
        "quality": o.get("quality_grade"),
        "taxon": taxon_names(o.get("taxon")),
        "guess": o.get("species_guess"),
        "observer": (o.get("user") or {}).get("login"),
        "obscured": obscured,
        "coords": coords,
        "photo": photos[0] if photos else None,
    }


def slim_species(r):
    t = r.get("taxon") or {}
    return {
        "count": r.get("count"),
        "taxon_id": t.get("id"),
        "url": f"{WEB}/taxa/{t.get('id')}" if t.get("id") else None,
        "taxon": taxon_names(t),
        "photo": photo(t.get("default_photo")),
    }


def links(s):
    q = urllib.parse.urlencode({k: v for k, v in filter_params(s).items() if k != "verifiable"})
    out = {
        "explore": f"{WEB}/observations?{q}",
        "place": f"{WEB}/places/{s['place_slug']}" if s.get("place_slug") else None,
        "project": f"{WEB}/projects/{s['project']}" if s.get("project") else None,
        "app": f"{WEB}/pages/getting+started",
    }
    return out


def load_previous(demo):
    if not OUT_FILE.exists():
        return None
    try:
        prev = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return prev if bool(prev.get("demo")) == bool(demo) else None


def update(cfg, demo=False, fetch=api_get, write=True, sleep=time.sleep):
    s = settings(cfg)
    flt = filter_params(s)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = {
        "fetched_at": now, "demo": bool(demo), "stale": False, "errors": [],
        "source": "project" if s.get("project") else "area",
        "project": s.get("project"),
        "filter": urllib.parse.urlencode(flt),
        "links": links(s),
        "attribution": "Observations and photos from iNaturalist, "
                       "each photo under the licence chosen by its observer.",
    }
    if demo:
        payload = dict(base, **make_demo(s))
    else:
        try:
            obs = fetch("/observations", dict(flt, order="desc", order_by="observed_on",
                                              per_page=s["recent"], photos="true",
                                              locale="en"))
            sleep(s["pause_s"])
            # Toutes les especes en une requete (500 au plus) : la page
            # Plants and animals les range par groupe, la page iNaturalist
            # n'affiche que les plus observees.
            spp = fetch("/observations/species_counts", dict(flt, per_page=s["max_species"],
                                                             locale="en"))
            sleep(s["pause_s"])
            ppl = fetch("/observations/observers", dict(flt, per_page=1))
        except Exception as e:
            prev = load_previous(demo=False)
            if prev is None:
                raise SystemExit(f"iNaturalist injoignable et aucun fichier précédent : {e}")
            prev["stale"] = True
            prev["errors"] = [f"{type(e).__name__}: {e}"[:160]]
            payload = prev
        else:
            payload = dict(base,
                           totals={"observations": obs.get("total_results", 0),
                                   "species": spp.get("total_results", 0),
                                   "observers": ppl.get("total_results", 0)},
                           top_species=s["top_species"],
                           recent=[slim_observation(o) for o in obs.get("results", [])],
                           species=[slim_species(r) for r in spp.get("results", [])])
    if write:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def make_demo(s):
    """Jeu synthetique, marque comme tel, pour tester sans reseau."""
    today = datetime.now(timezone.utc).date()
    pool = [
        ("Cladorhynchus leucocephalus", "Banded Stilt", "Aves", -28.89, 137.05),
        ("Tecticornia", "Samphires", "Plantae", -28.95, 137.02),
        ("Ctenophorus maculosus", "Lake Eyre Dragon", "Reptilia", None, None),
        ("Pelecanus conspicillatus", "Australian Pelican", "Aves", -29.02, 137.40),
    ]
    recent = []
    for i, (sci, common, group, lat, lng) in enumerate(pool):
        recent.append({
            "id": 1000 + i, "url": f"{WEB}/observations/{1000 + i}",
            "observed_on": str(today - timedelta(days=3 * i)),
            "quality": "research" if i % 2 == 0 else "needs_id",
            "taxon": {"name": sci, "common": common, "rank": "species", "group": group},
            "guess": common, "observer": f"demo_observer_{i}",
            "obscured": lat is None, "coords": [lat, lng] if lat is not None else None,
            "photo": None,
        })
    species = [{"count": 12 - 3 * i, "taxon_id": None, "url": None,
                "taxon": r["taxon"], "photo": None} for i, r in enumerate(recent)]
    return {"top_species": s["top_species"],
            "totals": {"observations": 42, "species": 17, "observers": 9},
            "recent": recent, "species": species}


def main():
    ap = argparse.ArgumentParser(description="Observations iNaturalist autour du lac")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--demo", action="store_true", help="Données synthétiques, sans réseau")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    d = update(cfg, demo=args.demo)
    t = d.get("totals", {})
    src = f"projet {d['project']}" if d.get("project") else "emprise du lac"
    print(f"JSON écrit : {OUT_FILE}  ({src}{', démonstration' if d.get('demo') else ''})")
    print(f"  {t.get('observations', 0)} observations, {t.get('species', 0)} espèces, "
          f"{t.get('observers', 0)} observateurs")
    shown = sum(1 for o in d.get("recent", []) if o.get("photo"))
    print(f"  {len(d.get('recent', []))} observations récentes, dont {shown} avec photo sous licence")
    if d.get("stale"):
        print("  iNaturalist injoignable : dernier jeu valide conservé")


if __name__ == "__main__":
    main()
