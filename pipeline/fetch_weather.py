#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recupere les dernieres observations meteo du BOM pour les stations
configurees (flux JSON "Latest Weather Observations", 72 h glissantes)
et ecrit data/weather.json pour le site.

Le pare-feu du BOM bloque les requetes sans User-Agent de navigateur :
la recuperation se fait donc cote serveur, avec l'UA de config.yaml.

Usage :
    python pipeline/fetch_weather.py          # recupere et ecrit le JSON
    python pipeline/fetch_weather.py --demo   # observations synthetiques
"""

import argparse
import json
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

WEATHER_FILE = ROOT / "data" / "weather.json"

COMPASS_DEG = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def _num(v):
    """Nombre ou None (le BOM code l'absence par '-' ou null)."""
    if v in (None, "-", ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slim_obs(o):
    """Reduit une observation BOM aux champs utilises par le site."""
    wind_dir = o.get("wind_dir") or None
    return {
        "utc": o.get("aifstime_utc"),
        "air_temp": _num(o.get("air_temp")),
        "rel_hum": _num(o.get("rel_hum")),
        "wind_dir": wind_dir,
        "wind_dir_deg": COMPASS_DEG.get(wind_dir),
        "wind_spd_kmh": _num(o.get("wind_spd_kmh")),
        "gust_kmh": _num(o.get("gust_kmh")),
        "rain_since_9am": _num(o.get("rain_trace")),
        "press_hpa": _num(o.get("press_qnh")) or _num(o.get("press")),
    }


def obs_time(rec):
    """Horodatage BOM 'YYYYMMDDHHMMSS' -> datetime UTC (ou None)."""
    utc = rec.get("utc")
    if not utc or len(utc) < 14:
        return None
    try:
        return datetime.strptime(utc[:14], "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def merge_history(previous, fresh, hours=48):
    """Fusionne l'historique conserve et le flux courant.

    Le BOM ne publie qu'une fenetre glissante : conserver les releves
    deja vus permet de tenir 48 h meme si le flux est tronque ou si une
    recuperation echoue. Retourne une liste chronologique.
    """
    by_time = {}
    for rec in list(previous or []) + list(fresh or []):
        if rec.get("utc"):
            by_time[rec["utc"]] = rec       # le flux frais ecrase l'ancien

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    kept = [r for r in by_time.values()
            if (obs_time(r) or cutoff) >= cutoff]
    return sorted(kept, key=lambda r: r["utc"])


def parse_station_payload(payload):
    """Flux BOM -> {latest, history}, history en ordre chronologique.
    Retourne None si le flux est vide."""
    data = (payload.get("observations") or {}).get("data") or []
    if not data:
        return None
    latest = slim_obs(data[0])              # sort_order 0 = plus recent
    latest["local_time"] = data[0].get("local_date_time_full")
    history = sorted((slim_obs(o) for o in data if o.get("aifstime_utc")),
                     key=lambda r: r["utc"])
    return {"latest": latest, "history": history}


def fetch_station_json(product, wmo, user_agent, timeout=12):
    url = f"https://www.bom.gov.au/fwo/{product}/{product}.{wmo}.json"
    req = urllib.request.Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_previous():
    """Dernier releve ecrit, indexe par nom de station (ou {})."""
    if not WEATHER_FILE.exists():
        return {}
    try:
        with open(WEATHER_FILE, "r", encoding="utf-8") as f:
            return {s["name"]: s for s in json.load(f).get("stations", [])}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def update(cfg, demo=False, write=True):
    """Recupere toutes les stations et (optionnellement) ecrit le JSON.

    Les echecs par station sont isoles : en cas d'echec, la derniere
    observation valide connue est conservee et marquee stale, plutot
    que d'etre effacee (une coupure BOM ne doit pas vider le site)."""
    wcfg = cfg.get("weather") or {}
    ua = wcfg.get("user_agent", "Mozilla/5.0")
    hours = wcfg.get("history_hours", 48)
    previous = load_previous()
    stations_out = []
    any_stale = False

    for st in wcfg.get("stations", []):
        entry = {"name": st["name"], "lat": st.get("lat"), "lon": st.get("lon"),
                 "ok": False, "latest": None, "history": []}
        error = None

        if demo:
            parsed = make_demo_station(st["name"])
        else:
            try:
                payload = fetch_station_json(st["product"], st["wmo"], ua)
                parsed = parse_station_payload(payload)
                if parsed is None:
                    error = "flux vide"
            except Exception as e:
                parsed, error = None, f"{type(e).__name__}: {e}"[:200]

        if parsed is not None:
            old = (previous.get(st["name"]) or {}).get("history") or []
            parsed["history"] = merge_history(old, parsed["history"], hours)
            entry.update(ok=True, **parsed)
        else:
            entry["error"] = error
            old = previous.get(st["name"])
            if old and old.get("latest"):
                # Conserve la derniere observation connue
                entry.update(ok=True, stale=True,
                             latest=old["latest"], history=old.get("history", []))
                any_stale = True

        stations_out.append(entry)

    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo": bool(demo),
        "stale": any_stale,
        "history_hours": hours,
        "source": "Bureau of Meteorology (observations 72 h)",
        "stations": stations_out,
    }
    if write:
        WEATHER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WEATHER_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def make_demo_station(name):
    """Observations synthetiques : vent de SE dominant, clairement etiquetees
    via le drapeau demo du payload."""
    rng = random.Random(hash(name) & 0xFFFF)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    dirs = ["SE", "SSE", "ESE", "S"]
    history = []
    for i in range(96):                 # 48 h a 30 min
        t = now - timedelta(minutes=30 * i)
        d = rng.choice(dirs)
        spd = round(max(4, rng.gauss(22, 6)))
        history.append({
            "utc": t.strftime("%Y%m%d%H%M%S"),
            "air_temp": round(rng.gauss(16, 3), 1),
            "rel_hum": round(max(10, min(95, rng.gauss(45, 12)))),
            "wind_dir": d,
            "wind_dir_deg": COMPASS_DEG[d],
            "wind_spd_kmh": spd,
            "gust_kmh": spd + rng.randint(5, 14),
            "rain_since_9am": 0.0,
            "press_hpa": round(rng.gauss(1018, 3), 1),
        })
    history.sort(key=lambda r: r["utc"])
    latest = dict(history[-1])
    latest["local_time"] = None
    return {"latest": latest, "history": history}


def main():
    parser = argparse.ArgumentParser(description="Observations BOM -> JSON")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    payload = update(cfg, demo=args.demo)
    print(f"JSON ecrit : {WEATHER_FILE}")
    for s in payload["stations"]:
        if s["ok"]:
            l = s["latest"]
            mark = "  (releve precedent conserve)" if s.get("stale") else ""
            print(f"  {s['name']}: {l['wind_dir'] or 'calme'} "
                  f"{l['wind_spd_kmh'] or 0:.0f} km/h, {l['air_temp']} °C{mark}")
        else:
            print(f"  {s['name']}: ECHEC — {s.get('error')}")


if __name__ == "__main__":
    main()
