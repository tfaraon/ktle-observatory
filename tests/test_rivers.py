#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stations de jaugeage du bassin (pipeline/fetch_rivers.py), sans reseau :
les reponses du service KiWIS de Water Data Online sont simulees dans
leur format documente.

Ce qui est verifie : seules les stations du bassin sont retenues (le
Bulloo voisin est exclu), les stations fermees sont ecartees en mode
automatique mais gardees si on les demande explicitement, les valeurs
manquantes sont ignorees, l'etat de chaque station (ecoulement, pas
d'ecoulement, hauteur seule, pas de donnee recente) et la reprise sur
le dernier jeu valide en cas de panne.

Execution :  python tests/test_rivers.py
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import fetch_rivers as fv  # noqa: E402

HEAD = ["station_no", "station_name", "station_latitude", "station_longitude",
        "ts_id", "ts_unitsymbol", "from", "to"]
Q = [HEAD,
     ["003103A", "Cooper Ck at Nappa Merrie", "-27.60", "141.11", "q1", "cumec", "1966-01-01", "2026-09-20T00:00:00.000+10:00"],
     ["003301A", "Barcoo R at Retreat", "-25.18", "143.26", "q2", "cumec", "1960-01-01", "1988-06-30"],
     ["011201A", "Bulloo R at Thargomindah", "-27.99", "143.83", "q3", "cumec", "1970-01-01", "2026-09-20"],
     ["DRY01", "Dry creek", "-26.0", "140.0", "q4", "cumec", "2000-01-01", "2026-09-19"]]
H = [HEAD,
     ["003103A", "Cooper Ck at Nappa Merrie", "-27.60", "141.11", "h1", "m", "1966-01-01", "2026-09-20"],
     ["LVL01", "Level only gauge", "-24.0", "139.0", "h5", "m", "2010-01-01", "2026-09-18"]]
VALUES = {
    "q1": [["2026-09-18T00:00:00.000+10:00", 12.5, 10], ["2026-09-19T00:00:00.000+10:00", None, 255],
           ["2026-09-20T00:00:00.000+10:00", 14.0, 10]],
    "q2": [["1988-06-30T00:00:00.000+10:00", 1.0, 10]],
    "q4": [["2026-09-19T00:00:00.000+10:00", 0.0, 10]],
    "h1": [["2026-09-20T00:00:00.000+10:00", 1.82, 10]],
    "h5": [["2026-09-18T00:00:00.000+10:00", 0.4, 10]],
}
calls = []


def fake(s, request, extra):
    calls.append((request, extra))
    if request == "getTimeseriesList":
        return Q if extra["parametertype_name"] == "Water Course Discharge" else H
    return [{"ts_id": extra["ts_id"], "columns": "Timestamp,Value,Quality Code",
             "data": VALUES.get(extra["ts_id"], [])}]


TODAY = date(2026, 9, 22)
with tempfile.TemporaryDirectory() as td:
    fv.OUT_FILE = Path(td) / "rivers.json"

    # ── Mode automatique : bassin et activité ──
    found = {st["station_no"]: st for st in fv.discover({}, call=fake, today=TODAY)}
    assert set(found) == {"003103A", "DRY01", "LVL01"}, set(found)
    assert "011201A" not in found, "Bulloo : hors du bassin"
    assert "003301A" not in found, "Retreat : fermée depuis 1988"
    assert set(found["003103A"]["series"]) == {"discharge", "level"}

    pauses = []
    p = fv.update({}, call=fake, today=TODAY, sleep=pauses.append)
    by = {st["station_no"]: st for st in p["stations"]}
    nm = by["003103A"]
    assert nm["discharge"]["values"] == [["2026-09-18", 12.5], ["2026-09-20", 14.0]], "valeur manquante ignorée"
    assert nm["discharge"]["last"] == {"date": "2026-09-20", "value": 14.0}
    assert nm["discharge"]["unit"] == "cumec" and nm["level"]["last"]["value"] == 1.82
    assert nm["status"] == "flowing"
    assert by["DRY01"]["status"] == "no flow"
    assert by["LVL01"]["status"] == "level only"
    assert len(pauses) == 4 and all(x >= 0.5 for x in pauses), "requêtes espacées"
    assert p["selection"] == "auto" and p["licence"].startswith("Creative Commons")
    # Moyennes journalières contrôlées, sur la bonne période
    lists = [c for c in calls if c[0] == "getTimeseriesList"]
    assert all(c[1]["ts_name"] == "DMQaQc.Merged.DailyMean.24HR" for c in lists)
    vals = [c for c in calls if c[0] == "getTimeseriesValues"]
    assert vals[0][1]["from"] == "2025-09-22" and vals[0][1]["to"] == "2026-09-22"

    # ── Liste explicite : une station fermée reste disponible pour l'historique ──
    p2 = fv.update({"rivers": {"stations": ["003301A"]}}, call=fake, today=TODAY,
                   sleep=lambda x: None, write=False)
    assert [st["station_no"] for st in p2["stations"]] == ["003301A"]
    assert p2["stations"][0]["status"] == "no recent data" and p2["selection"] == "list"

    # ── Panne : dernier jeu gardé ──
    def dead(s, request, extra):
        raise OSError("réseau coupé")
    p3 = fv.update({}, call=dead, today=TODAY)
    assert p3["stale"] is True and p3["stations"]

print("OK — stations du bassin seulement, stations fermées écartées ou gardées sur demande, "
      "valeurs manquantes ignorées, états des stations, requêtes espacées, panne.")
