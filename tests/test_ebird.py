#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la recuperation eBird (pipeline/fetch_ebird.py), sans reseau.

Les reponses de l'API sont simulees. Les controles portent sur ce qui
engage le projet vis-a-vis d'eBird et des observateurs : la cle ne doit
jamais apparaitre dans le fichier publie, les lieux prives ne doivent pas
reveler leur emplacement, la source doit etre citee, et une panne ne doit
ni effacer le dernier jeu valide ni melanger demonstration et reel.

Execution :  python tests/test_ebird.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import fetch_ebird as fe  # noqa: E402

KEY = "SECRET-KEY-123"
CFG = {"ebird": {"back_days": 30, "dist_km": 50, "hotspots": False, "pause_s": 0, "points": [
    {"name": "A", "lat": -28.9, "lon": 137.0},
    {"name": "B", "lat": -28.9, "lon": 137.5}]}}


def obs(code, sci, dt, private=False, loc="Hotspot", lat=-28.9, lng=137.1):
    return {"speciesCode": code, "comName": code.title(), "sciName": sci,
            "howMany": 3, "obsDt": dt, "locId": "L1", "locName": loc,
            "lat": lat, "lng": lng, "obsValid": True, "obsReviewed": False,
            "locationPrivate": private, "subId": "S999",
            "userDisplayName": "Observer Name"}


RESPONSES = {
    ("A", "recent"): [obs("bansti1", "Cladorhynchus leucocephalus", "2026-09-01 08:00"),
                      obs("zebfin2", "Taeniopygia castanotis", "2026-09-10 07:00",
                          private=True, loc="My backyard", lat=-28.95, lng=137.2)],
    ("B", "recent"): [obs("bansti1", "Cladorhynchus leucocephalus", "2026-09-12 17:30"),
                      obs("auspel1", "Pelecanus conspicillatus", "2026-09-05")],
    ("A", "notable"): [],
    ("B", "notable"): [obs("auspel1", "Pelecanus conspicillatus", "2026-09-05")],
}


def fake_get(fail=()):
    def get(path, params, key, timeout=20):
        assert key == KEY
        name = "A" if params["lng"] == 137.0 else "B"
        if name in fail:
            raise OSError("network down")
        kind = "notable" if path.endswith("notable") else "recent"
        assert params["back"] <= 30 and params["dist"] <= 50
        return RESPONSES[(name, kind)]
    return get


with tempfile.TemporaryDirectory() as td:
    fe.EBIRD_FILE = Path(td) / "ebird.json"

    # ── Récupération normale ─────────────────────────────────
    fe.api_get = fake_get()
    data = fe.update(CFG, key=KEY)
    text = fe.EBIRD_FILE.read_text(encoding="utf-8")

    assert KEY not in text, "la clé ne doit jamais être écrite"
    assert "Observer Name" not in text and "S999" not in text, \
        "aucun nom d'observateur ni identifiant de liste"
    assert "eBird.org" in data["attribution"] and data["attribution_url"]

    codes = [r["speciesCode"] for r in data["species"]]
    assert sorted(codes) == ["auspel1", "bansti1", "zebfin2"], codes
    # Une espèce vue aux deux points : seule la plus récente reste
    stilt = next(r for r in data["species"] if r["speciesCode"] == "bansti1")
    assert stilt["obsDt"] == "2026-09-12 17:30", stilt
    # Tri du plus récent au plus ancien
    assert codes[0] == "bansti1"

    # Lieu privé : espèce conservée, emplacement retiré
    finch = next(r for r in data["species"] if r["speciesCode"] == "zebfin2")
    assert finch["lat"] is None and finch["lng"] is None
    assert finch["locName"] is None and finch["locId"] is None
    assert "My backyard" not in text

    # Indicateurs et observations notables
    assert stilt["indicator"] and not finch["indicator"]
    pelican = next(r for r in data["species"] if r["speciesCode"] == "auspel1")
    assert pelican["notable"] and not stilt["notable"]
    ind = {i["sciName"]: i for i in data["indicators"]}
    assert ind["Cladorhynchus leucocephalus"]["present"]
    assert not ind["Recurvirostra novaehollandiae"]["present"]
    assert data["demo"] is False and data["stale"] is False

    # ── Un point en panne : résultat partiel, signalé ────────
    fe.api_get = fake_get(fail=("B",))
    part = fe.update(CFG, key=KEY)
    assert part["partial"] and len(part["errors"]) == 1
    assert [r["speciesCode"] for r in part["species"]] == ["zebfin2", "bansti1"]
    assert KEY not in json.dumps(part["errors"]), "la clé ne doit pas fuir via les erreurs"

    # ── Panne totale : le dernier jeu valide est conservé ────
    fe.api_get = fake_get()
    fe.update(CFG, key=KEY)
    fe.api_get = fake_get(fail=("A", "B"))
    kept = fe.update(CFG, key=KEY)
    assert kept["stale"] is True and kept["n_species"] == 3
    assert json.loads(fe.EBIRD_FILE.read_text())["stale"] is True

    # ── Démonstration et réel ne se mélangent pas ────────────
    demo = fe.update(CFG, demo=True)
    assert demo["demo"] is True and demo["n_species"] >= 5
    assert all("demonstration" in (r["locName"] or "") for r in demo["species"])
    # Un fichier de démonstration ne sert jamais de repli au réel
    fe.api_get = fake_get(fail=("A", "B"))
    try:
        fe.update(CFG, key=KEY)
        raise AssertionError("un repli sur la démonstration aurait été accepté")
    except SystemExit as e:
        assert "injoignable" in str(e)

    # ── Clé absente : message clair, rien d'écrit ────────────
    before = fe.EBIRD_FILE.read_text()
    try:
        fe.update(CFG, key=None)
        raise AssertionError("une erreur était attendue")
    except SystemExit as e:
        assert "EBIRD_API_KEY" in str(e) and "keygen" in str(e)
    assert fe.EBIRD_FILE.read_text() == before

    # ── Bornes de l'API respectées ───────────────────────────
    seen = {}

    def capture(path, params, key, timeout=20):
        seen.update(params)
        return []
    fe.api_get = capture
    fe.update({"ebird": {"back_days": 90, "dist_km": 200, "hotspots": False, "pause_s": 0,
                         "points": [{"name": "A", "lat": 0, "lon": 0}]}}, key=KEY)
    assert seen["back"] == 30 and seen["dist"] == 50, seen

print("OK — clé et observateurs absents du fichier, lieux privés masqués, "
      "fusion entre points, indicateurs et espèces notables, pannes "
      "partielle et totale, séparation démonstration/réel, bornes de l'API.")


# ══════════════════════════════════════════════════════════════
# La cle ne doit jamais atteindre le navigateur ni le depot.
#
# Le site statique est public : un appel a l'API eBird depuis le
# JavaScript exposerait la cle a tous. Tout passe par le pipeline, et
# le workflow lit la cle dans les secrets du depot.
# ══════════════════════════════════════════════════════════════

import re as _re  # noqa: E402

FRONT = ROOT / "frontend"
for js in FRONT.glob("*.js"):
    text = js.read_text(encoding="utf-8")
    assert "api.ebird.org" not in text, f"{js.name} appelle l'API eBird directement"
    assert "x-ebirdapitoken" not in text.lower(), f"{js.name} manipule la clé"
html = (FRONT / "index.html").read_text(encoding="utf-8")
assert "api.ebird.org" not in html

import yaml as _yaml  # noqa: E402

cfg_text = (ROOT / "config.yaml").read_text(encoding="utf-8")
ecfg = (_yaml.safe_load(cfg_text) or {}).get("ebird") or {}
assert not any(k.lower() in ("key", "api_key", "token") for k in ecfg), \
    "la clé ne doit pas figurer dans config.yaml"

wf = (ROOT / ".github" / "workflows" / "ebird.yml").read_text(encoding="utf-8")
assert "secrets.EBIRD_API_KEY" in wf, "le workflow doit lire la clé dans les secrets"
assert not _re.search(r"EBIRD_API_KEY:\s*['\"]?[A-Za-z0-9]{6,}", wf), \
    "une clé en clair dans le workflow"

# ── Route du serveur : elle sert le fichier, sans interroger eBird ──
sys.path.insert(0, str(ROOT / "backend"))
import app as backend  # noqa: E402

client = backend.app.test_client()
saved = backend.EBIRD_FILE
with tempfile.TemporaryDirectory() as td:
    backend.EBIRD_FILE = Path(td) / "absent.json"
    r = client.get("/api/ebird")
    assert r.status_code == 404 and r.get_json()["error"] == "no_data"
    backend.EBIRD_FILE = Path(td) / "ebird.json"
    backend.EBIRD_FILE.write_text(json.dumps({"species": [], "demo": True}),
                                  encoding="utf-8")
    r = client.get("/api/ebird")
    assert r.status_code == 200 and r.get_json()["demo"] is True
backend.EBIRD_FILE = saved

print("OK — aucun appel direct ni clé côté navigateur, clé absente de la "
      "configuration et lue dans les secrets, route du serveur sans réseau.")
