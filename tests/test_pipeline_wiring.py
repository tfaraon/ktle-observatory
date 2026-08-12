#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de cablage du pipeline (sans dependances SWOT).

Verifie, en substituant extract_wse_timeseries_parallel par un stub :
  - que les parametres du config.yaml sont bien transmis a la toolbox ;
  - le filtrage temporel (date_min) et le datum_offset ;
  - que "latest" correspond bien a l'observation la plus recente ;
  - le schema du JSON produit.

Execution :  python tests/test_pipeline_wiring.py
"""

import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

# ── Stub de SWOT_toolbox.SWOT_tools ──────────────────────────
calls = []

def fake_extract(**kwargs):
    calls.append(kwargs)
    return pd.DataFrame({
        "date": [datetime(2024, 12, 20, 3, 0),   # avant date_min -> exclue
                 datetime(2025, 3, 10, 3, 15),
                 datetime(2025, 6, 1, 2, 45),
                 datetime(2025, 5, 2, 3, 5)],    # desordonnee volontairement
        "wse": [-15.9, -13.42, -11.87, -12.55],
        "filename": ["a", "b", "c", "d"],
        "pass": ["u"] * 4, "resolution": ["u"] * 4, "tile": ["u"] * 4,
    })

fake_tools = types.ModuleType("SWOT_toolbox.SWOT_tools")
fake_tools.extract_wse_timeseries_parallel = fake_extract
fake_pkg = types.ModuleType("SWOT_toolbox")
fake_pkg.SWOT_tools = fake_tools
sys.modules["SWOT_toolbox"] = fake_pkg
sys.modules["SWOT_toolbox.SWOT_tools"] = fake_tools

import update_swot  # noqa: E402

# ── Configuration de test ────────────────────────────────────
cfg = {
    "lake": {"name": "Test", "center": {"lat": -28.9, "lon": 137.35}, "zoom": 8},
    "paths": {"swot_data": "/tmp/fake_swot", "output_json": "/tmp/test_wse.json"},
    "extraction": {
        "buffer_size": 6,
        "wse_qual_filter": [0, 1, 2],
        "filter_outliers": True,
        "filter_bound": True,
        "filter_resolution": None,
        "date_min": "2025-01-01",
        "date_max": None,
    },
    "sites": [{"name": "Belt Bay", "lon": 137.56, "lat": -28.893,
               "datum_offset": 0.5}],
    "display": {"datum_label": "WSE (m)"},
}

# ── Execution ────────────────────────────────────────────────
sites = update_swot.extract_sites(cfg)
out = update_swot.write_payload(cfg, sites, demo=False, output="/tmp/test_wse.json")

# ── Assertions ───────────────────────────────────────────────
kw = calls[0]
assert kw["lon"] == 137.56 and kw["lat"] == -28.893
assert kw["buffer_size"] == 6
assert kw["wse_qual_filter"] == [0, 1, 2]
assert kw["filter_outliers"] is True and kw["filter_bound"] is True
assert kw["filter_resolution"] is None

site = sites[0]
assert len(site["series"]) == 3, "l'observation anterieure a date_min doit etre exclue"
dates = [r["date"] for r in site["series"]]
assert dates == sorted(dates), "la serie doit etre triee par date"
assert site["latest"]["date"].startswith("2025-06-01"), "latest = date max"
assert abs(site["latest"]["wse"] - (-11.87 + 0.5)) < 1e-9, "datum_offset applique"
assert site["stats"]["n"] == 3

payload = json.loads(Path(out).read_text())
for key in ("generated_at", "demo", "lake", "datum_label", "sites"):
    assert key in payload
assert payload["demo"] is False

print("OK — cablage pipeline <-> SWOT_toolbox valide "
      f"(latest {site['latest']['wse']} m le {site['latest']['date']}).")
