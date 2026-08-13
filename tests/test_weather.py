#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du module meteo BOM (sans acces reseau).

Verifie :
  - le parsing d'un flux BOM realiste (derniere observation en tete) ;
  - la gestion des valeurs manquantes ('-' et null -> None) ;
  - la conversion rose des vents -> degres ;
  - le flux vide -> None ;
  - l'isolation des echecs : une station en erreur n'empeche pas les
    autres d'etre servies ;
  - le schema du payload ecrit.

Execution :  python tests/test_weather.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import fetch_weather as fw  # noqa: E402

# ── Flux BOM realiste (extrait des champs utilises) ──────────
PAYLOAD = {
    "observations": {
        "data": [
            {   # sort_order 0 = observation la plus recente
                "sort_order": 0,
                "aifstime_utc": "20260810T003000",
                "local_date_time_full": "20260810100000",
                "air_temp": 15.6,
                "rel_hum": 52,
                "wind_dir": "SSE",
                "wind_spd_kmh": 31,
                "gust_kmh": 43,
                "rain_trace": "0.0",
                "press_qnh": 1017.4,
            },
            {
                "sort_order": 1,
                "aifstime_utc": "20260810T000000",
                "air_temp": 15.1,
                "rel_hum": None,        # valeur absente (null)
                "wind_dir": "SE",
                "wind_spd_kmh": 28,
                "gust_kmh": "-",        # valeur absente (tiret BOM)
                "rain_trace": "0.0",
                "press_qnh": 1017.2,
            },
        ]
    }
}

parsed = fw.parse_station_payload(PAYLOAD)
latest = parsed["latest"]

assert latest["utc"] == "20260810T003000", "latest = premiere entree du flux"
assert latest["air_temp"] == 15.6 and latest["rel_hum"] == 52.0
assert latest["wind_dir"] == "SSE" and latest["wind_dir_deg"] == 157.5
assert latest["wind_spd_kmh"] == 31.0 and latest["gust_kmh"] == 43.0
assert latest["press_hpa"] == 1017.4
assert latest["local_time"] == "20260810100000"
assert len(parsed["history"]) == 2
# L'historique est chronologique : le plus recent en dernier
assert parsed["history"][-1]["utc"] == "20260810T003000"
assert parsed["history"][0]["utc"] == "20260810T000000"

first = parsed["history"][0]
assert first["rel_hum"] is None, "null -> None"
assert first["gust_kmh"] is None, "'-' -> None"

# ── Rose des vents complete ──────────────────────────────────
assert fw.COMPASS_DEG["N"] == 0 and fw.COMPASS_DEG["W"] == 270
assert len(fw.COMPASS_DEG) == 16
assert fw.slim_obs({"wind_dir": "CALM"})["wind_dir_deg"] is None

# ── Flux vide ────────────────────────────────────────────────
assert fw.parse_station_payload({"observations": {"data": []}}) is None
assert fw.parse_station_payload({}) is None

# ── Isolation des echecs par station ─────────────────────────
calls = []

def fake_fetch(product, wmo, user_agent, timeout=12):
    calls.append((product, wmo))
    if wmo == "99999":
        raise TimeoutError("timed out")
    return PAYLOAD

fw.fetch_station_json = fake_fetch

cfg = {"weather": {"user_agent": "UA-test", "stations": [
    {"name": "Marree Airport", "product": "IDS60801", "wmo": "95480",
     "lat": -29.66, "lon": 138.065},
    {"name": "Station HS", "product": "IDS60801", "wmo": "99999",
     "lat": -28.0, "lon": 137.0},
]}}

with tempfile.TemporaryDirectory() as td:
    fw.WEATHER_FILE = Path(td) / "weather.json"
    payload = fw.update(cfg)

    assert calls == [("IDS60801", "95480"), ("IDS60801", "99999")]
    ok, ko = payload["stations"]
    assert ok["ok"] is True and ok["latest"]["wind_spd_kmh"] == 31.0
    assert ko["ok"] is False and "TimeoutError" in ko["error"]
    assert ko["latest"] is None, "une station en echec ne casse pas le payload"
    assert payload["stale"] is False, "aucun releve precedent a conserver"

    for key in ("fetched_at", "demo", "stale", "source", "stations"):
        assert key in payload
    written = json.loads(fw.WEATHER_FILE.read_text(encoding="utf-8"))
    assert written["stations"][0]["name"] == "Marree Airport"

    # ── Conservation du dernier releve valide ────────────────
    # La station 95480, valide au tour precedent, echoue maintenant :
    # son observation doit etre conservee et marquee stale.
    def all_fail(product, wmo, user_agent, timeout=12):
        raise ConnectionError("BOM injoignable")

    fw.fetch_station_json = all_fail
    payload2 = fw.update(cfg)
    kept = payload2["stations"][0]
    assert kept["ok"] is True and kept["stale"] is True
    assert kept["latest"]["wind_spd_kmh"] == 31.0, "observation conservee"
    assert "ConnectionError" in kept["error"]
    assert payload2["stale"] is True
    # La station jamais recuperee reste vide
    assert payload2["stations"][1]["latest"] is None

    fw.fetch_station_json = fake_fetch  # restaure pour la suite

# ── Mode demo ────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    fw.WEATHER_FILE = Path(td) / "weather.json"
    demo = fw.update(cfg, demo=True)
    assert demo["demo"] is True
    assert all(s["ok"] for s in demo["stations"]), "demo : toutes les stations OK"
    # Le generateur couvre 7 j a 30 min (336 releves) ; la fenetre
    # d'archive de cette configuration (48 h par defaut) les tronque.
    assert len(demo["stations"][0]["history"]) == 96, "48 h a 30 min"

# ══════════════════════════════════════════════════════════════
# Archive glissante de 48 h
# ══════════════════════════════════════════════════════════════

from datetime import datetime, timedelta, timezone  # noqa: E402


def rec(dt, spd=20.0):
    return {"utc": dt.strftime("%Y%m%d%H%M%S"), "wind_spd_kmh": spd,
            "air_temp": 15.0, "rel_hum": 50.0, "wind_dir": "SE",
            "wind_dir_deg": 135.0, "gust_kmh": spd + 8, "press_hpa": 1015.0,
            "rain_since_9am": 0.0}


now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

# Releves conserves (anciens) + flux courant (recents) -> fusion
previous = [rec(now - timedelta(hours=h)) for h in range(47, 20, -1)]
fresh = [rec(now - timedelta(hours=h), spd=30.0) for h in range(24, -1, -1)]
merged = fw.merge_history(previous, fresh, hours=48)

utcs = [r["utc"] for r in merged]
assert utcs == sorted(utcs), "historique chronologique"
assert len(utcs) == len(set(utcs)), "pas de doublon d'horodatage"
# 27 releves conserves (h-47 a h-21) + 25 frais (h-24 a h-0),
# dont 4 horodatages communs -> 48 uniques
assert len(merged) == 48, len(merged)
assert merged[-1]["wind_spd_kmh"] == 30.0, "le flux frais est le plus recent"

# Le flux frais ecrase la valeur conservee au meme horodatage
same = now - timedelta(hours=22)
merged2 = fw.merge_history([rec(same, spd=5.0)], [rec(same, spd=42.0)])
assert len(merged2) == 1 and merged2[0]["wind_spd_kmh"] == 42.0

# Au-dela de la fenetre, les releves sont abandonnes
old = [rec(now - timedelta(hours=h)) for h in (72, 60, 49)]
assert fw.merge_history(old, [rec(now)], hours=48) == [rec(now)]

# Une recuperation ratee ne doit pas vider l'archive : le releve
# precedent est conserve avec son historique
with tempfile.TemporaryDirectory() as td:
    fw.WEATHER_FILE = Path(td) / "weather.json"

    def ok_fetch(product, wmo, user_agent, timeout=12):
        return {"observations": {"data": [
            {"aifstime_utc": (now - timedelta(minutes=30 * k)).strftime(
                "%Y%m%d%H%M%S"), "air_temp": 15.0, "wind_dir": "SE",
             "wind_spd_kmh": 25, "gust_kmh": 33, "rain_trace": "0.0",
             "press_qnh": 1015.0, "rel_hum": 50}
            for k in range(96)]}}

    fw.fetch_station_json = ok_fetch
    cfg1 = {"weather": {"user_agent": "UA", "history_hours": 48, "stations": [
        {"name": "Marree Airport", "product": "IDS60801", "wmo": "95480"}]}}
    p1 = fw.update(cfg1)
    n_hist = len(p1["stations"][0]["history"])
    assert n_hist == 96, n_hist
    assert p1["history_hours"] == 48

    def dead_fetch(product, wmo, user_agent, timeout=12):
        raise ConnectionError("BOM down")

    fw.fetch_station_json = dead_fetch
    p2 = fw.update(cfg1)
    st = p2["stations"][0]
    assert st["ok"] is True and st["stale"] is True
    assert len(st["history"]) == n_hist, "l'archive survit a une panne"

print("OK — parsing BOM, valeurs manquantes, rose des vents, flux vide, "
      "isolation des echecs et mode demo valides.")
print("OK — archive glissante de 48 h : fusion, dedoublonnage, purge "
      "au-dela de la fenetre et survie aux pannes validees.")

# ══════════════════════════════════════════════════════════════
# Démo et réel ne doivent jamais se mélanger.
#
# Le générateur de démonstration tire un bruit blanc gaussien (moyenne
# 22 km/h, écart-type 6) : fusionné avec des observations réelles, il
# produit une série qui saute de 15–25 km/h d'un relevé au suivant,
# là où le vent réel varie continûment.
# ══════════════════════════════════════════════════════════════

with tempfile.TemporaryDirectory() as td:
    fw.WEATHER_FILE = Path(td) / "weather.json"
    cfg_one = {"weather": {"user_agent": "UA", "history_hours": 168,
                           "stations": [{"name": "Marree Airport",
                                         "product": "IDS60801",
                                         "wmo": "95480"}]}}

    # 1. Un passage en mode démo remplit l'archive de bruit
    demo_payload = fw.update(cfg_one, demo=True)
    assert demo_payload["demo"] is True
    n_demo = len(demo_payload["stations"][0]["history"])
    assert n_demo == 336
    assert all(r.get("src") == "demo"
               for r in demo_payload["stations"][0]["history"])

    # 2. Une récupération réelle ne doit RIEN en reprendre
    def real_fetch(product, wmo, user_agent, timeout=12):
        base = datetime.now(timezone.utc)
        return {"observations": {"data": [
            {"aifstime_utc": (base - timedelta(minutes=30 * k)).strftime(
                "%Y%m%d%H%M%S"),
             "air_temp": 15.0, "wind_dir": "SE", "wind_spd_kmh": 20,
             "gust_kmh": 28, "rain_trace": "0.0", "press_qnh": 1015.0,
             "rel_hum": 50}
            for k in range(6)]}}

    fw.fetch_station_json = real_fetch
    real_payload = fw.update(cfg_one, demo=False)
    hist = real_payload["stations"][0]["history"]
    assert real_payload["demo"] is False
    assert len(hist) == 6, f"{len(hist)} relevés : l'archive démo a fui"
    assert all(r.get("src") == "bom" for r in hist)
    # Toutes les vitesses viennent du flux réel
    assert {r["wind_spd_kmh"] for r in hist} == {20.0}

    # 3. Symétrique : un passage démo ne reprend pas le réel
    demo_again = fw.update(cfg_one, demo=True)
    assert all(r.get("src") == "demo"
               for r in demo_again["stations"][0]["history"])

# 4. merge_history écarte toute provenance étrangère
now2 = datetime.now(timezone.utc).replace(second=0, microsecond=0)
mixed_prev = [dict(rec(now2 - timedelta(hours=2), spd=99.0), src="demo")]
fresh_real = [dict(rec(now2 - timedelta(hours=1), spd=18.0), src="bom")]
merged3 = fw.merge_history(mixed_prev, fresh_real, hours=48)
assert len(merged3) == 1 and merged3[0]["wind_spd_kmh"] == 18.0, merged3

print("OK — les observations réelles et les données de démonstration ne "
      "peuvent plus se mélanger dans l'archive.")
