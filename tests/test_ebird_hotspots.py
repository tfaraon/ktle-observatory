#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Couverture eBird de l'emprise et hotspots (pipeline/fetch_ebird.py), sans
reseau.

Muloorina manquait sur le site : a 52 km du point de requete le plus
proche, il echappait au rayon de 50 km que l'API impose. Ce test
verifie que la grille couvre toute l'emprise sans trou, que chaque
hotspot de l'emprise est retenu une fois, actif ou non, que les
observations ne sont demandees que pour les hotspots actifs, et que
leurs especes rejoignent la liste generale.

Execution :  python tests/test_ebird_hotspots.py
"""

import json
import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import fetch_ebird as fe  # noqa: E402

AREA = [136.3, -29.9, 138.4, -27.5]
KEY = "test-key-0000"


def km(a, b):
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    x = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0]))
         * math.sin(dlon / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(x))


# ── La grille couvre toute l'emprise, coins et spots compris ──
pts = fe.grid_points(AREA, 50)
w, s, e, n = AREA
samples = [(s + (n - s) * i / 40, w + (e - w) * j / 40) for i in range(41) for j in range(41)]
samples += [(-29.24, 137.91), (-29.65, 138.06), (-28.91, 136.34), (-29.40, 136.79)]
worst = max(min(km(q, (p["lat"], p["lon"])) for p in pts) for q in samples)
assert worst < 50, f"trou de couverture : {worst:.1f} km"
mul = min(km((-29.24, 137.91), (p["lat"], p["lon"])) for p in pts)
assert mul < 50, mul
assert len(pts) <= 20, len(pts)

# ── Hotspots : tous, une fois, dans l'emprise ; observations des actifs ──
recent_day = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%d %H:%M")
HOTSPOTS = [
    {"locId": "L100", "locName": "Muloorina Station", "lat": -29.24, "lng": 137.91,
     "latestObsDt": recent_day, "numSpeciesAllTime": 131},
    {"locId": "L200", "locName": "Halligan Bay", "lat": -28.52, "lng": 137.03,
     "latestObsDt": "2024-05-02 10:00", "numSpeciesAllTime": 41},
    {"locId": "L300", "locName": "Oodnadatta", "lat": -27.55, "lng": 135.45,
     "latestObsDt": recent_day, "numSpeciesAllTime": 90},
]
MUL_OBS = [{"speciesCode": "bansti1", "comName": "Banded Stilt", "sciName": "Cladorhynchus leucocephalus",
            "obsDt": recent_day, "howMany": 250, "locId": "L100", "locName": "Muloorina Station",
            "lat": -29.24, "lng": 137.91, "obsValid": True, "obsReviewed": False,
            "locationPrivate": False, "userDisplayName": "Somebody"},
           {"speciesCode": "crepig1", "comName": "Crested Pigeon", "sciName": "Ocyphaps lophotes",
            "obsDt": recent_day, "howMany": 6, "locId": "L100", "locName": "Muloorina Station",
            "lat": -29.24, "lng": 137.91, "obsValid": True, "obsReviewed": False,
            "locationPrivate": False}]
calls = []


def fake(path, params, key, timeout=20):
    calls.append((path, dict(params)))
    assert key == KEY
    if path == "/ref/hotspot/geo":
        assert params["fmt"] == "json" and params["dist"] <= 50
        if abs(params["lat"] - pts[0]["lat"]) < 1e-9 and abs(params["lng"] - pts[0]["lon"]) < 1e-9:
            raise OSError("un point en panne")
        return HOTSPOTS
    if path.startswith("/data/obs/L"):
        return MUL_OBS if "L100" in path else []
    return []


with tempfile.TemporaryDirectory() as td:
    fe.EBIRD_FILE = Path(td) / "ebird.json"
    fe.api_get = fake
    fe.SLEEP = lambda x: None
    data = fe.update({"ebird": {"area": AREA, "dist_km": 50, "back_days": 30}}, key=KEY)

    hs = {h["locId"]: h for h in data["hotspots"]}
    assert set(hs) == {"L100", "L200"}, "Oodnadatta est hors de l'emprise"
    assert hs["L100"]["name"] == "Muloorina Station" and hs["L100"]["numSpeciesAllTime"] == 131
    assert [r["speciesCode"] for r in hs["L100"]["recent"]] == ["bansti1", "crepig1"]
    assert hs["L100"]["recent"][0]["indicator"] is True
    assert hs["L200"]["recent"] == [], "hotspot sans visite récente : listé, sans requête"
    obs_calls = [c for c in calls if c[0].startswith("/data/obs/L")]
    assert [c[0] for c in obs_calls] == ["/data/obs/L100/recent"], obs_calls
    assert any("hotspots Grid 1" in e for e in data["errors"]), "panne d'un point signalée"
    # Les espèces du hotspot rejoignent la liste générale
    assert "crepig1" in {sp["speciesCode"] for sp in data["species"]}
    assert data["area"] == AREA and len(data["points"]) == len(pts)
    # Pas de nom d'observateur dans le fichier
    assert "Somebody" not in fe.EBIRD_FILE.read_text(encoding="utf-8")

print(f"OK — grille de {len(pts)} points sans trou (écart maximal {worst:.0f} km, Muloorina "
      f"à {mul:.0f} km), hotspots de l'emprise tous retenus une fois, observations des seuls "
      "actifs, espèces fusionnées, panne d'un point tolérée.")
