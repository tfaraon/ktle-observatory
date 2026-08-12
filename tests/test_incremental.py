#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de l'extraction incrementale et des utilitaires de mise a jour.

Verifie, avec un stub de SWOT_toolbox.SWOT_tools._process_file :
  - 1re execution : tous les fichiers traites, cache rempli ;
  - 2e execution : zero fichier retraite, serie identique ;
  - ajout d'un fichier : seul le nouveau est traite ;
  - changement de parametre (buffer) : cache invalide, tout retraite ;
  - filtres aval fideles a extract_wse_timeseries_parallel
    (bornes [-16, 6] puis IQR, actifs si n >= 4) ;
  - compute_since_date et filter_new_granules.

Execution :  python tests/test_incremental.py
"""

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

# ── Stub de SWOT_toolbox.SWOT_tools ──────────────────────────
# Valeurs par fichier : -20.0 exclue par les bornes, 0.5 par l'IQR.
VALUES = {
    "SWOT_L2_HR_Raster_100m_A_20250310T031500_x.nc": -13.0,
    "SWOT_L2_HR_Raster_100m_B_20250331T031500_x.nc": -12.8,
    "SWOT_L2_HR_Raster_100m_C_20250421T031500_x.nc": -12.9,
    "SWOT_L2_HR_Raster_100m_D_20250512T031500_x.nc": -20.0,
    "SWOT_L2_HR_Raster_100m_E_20250602T031500_x.nc": 0.5,
    "SWOT_L2_HR_Raster_100m_F_20250623T031500_x.nc": -13.1,
}
NEW_FILE = "SWOT_L2_HR_Raster_100m_G_20250714T031500_x.nc"

calls = []

def fake_process_file(file_path, lon, lat, buffer_size, wse_qual_filter, debug):
    calls.append(file_path)
    name = Path(file_path).name
    wse = VALUES.get(name)
    if wse is None:
        return None
    date = datetime.strptime(name.split("_")[6][:15], "%Y%m%dT%H%M%S")
    return {"date": date, "wse": wse, "filename": file_path,
            "pass": "Unknown", "resolution": "Unknown", "tile": "Unknown"}

fake_tools = types.ModuleType("SWOT_toolbox.SWOT_tools")
fake_tools._process_file = fake_process_file
fake_pkg = types.ModuleType("SWOT_toolbox")
fake_pkg.SWOT_tools = fake_tools
sys.modules["SWOT_toolbox"] = fake_pkg
sys.modules["SWOT_toolbox.SWOT_tools"] = fake_tools

import update_swot  # noqa: E402


def make_cfg(tmp, buffer_size=6):
    return {
        "lake": {"name": "Test", "center": {"lat": -28.9, "lon": 137.35}, "zoom": 8},
        "paths": {
            "swot_data": str(tmp / "granules"),
            "output_json": str(tmp / "wse.json"),
            "cache": str(tmp / "cache.json"),
        },
        "extraction": {
            "buffer_size": buffer_size,
            "wse_qual_filter": [0, 1, 2],
            "filter_outliers": True,
            "filter_bound": True,
            "filter_resolution": None,
            "date_min": None,
            "date_max": None,
            "n_workers": 1,
        },
        "sites": [{"name": "Belt Bay", "lon": 137.56, "lat": -28.893,
                   "datum_offset": 0.0}],
        "display": {"datum_label": "WSE (m)"},
    }


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    gdir = tmp / "granules"
    gdir.mkdir()
    for name in VALUES:
        (gdir / name).write_bytes(b"x" * 16)

    cfg = make_cfg(tmp)

    # ── 1re execution : tout est traite ──────────────────────
    calls.clear()
    sites, source = update_swot.extract_sites_incremental(cfg)
    assert len(calls) == 6, f"6 fichiers attendus, {len(calls)} traites"
    assert source["n_granules"] == 6 and source["new_this_run"] == 6
    assert source["last_granule_date"].startswith("2025-06-23")

    s = sites[0]
    # bornes : -20.0 exclue ; IQR sur le reste : 0.5 exclue -> 4 valeurs
    assert s["stats"]["n"] == 4, f"4 obs attendues, {s['stats']['n']}"
    kept = {r["wse"] for r in s["series"]}
    assert kept == {-13.0, -12.8, -12.9, -13.1}, kept
    assert s["latest"]["wse"] == -13.1 and s["latest"]["date"].startswith("2025-06-23")

    # ── 2e execution : cache -> aucun retraitement ───────────
    calls.clear()
    sites2, source2 = update_swot.extract_sites_incremental(cfg)
    assert len(calls) == 0, "le cache doit eviter tout retraitement"
    assert source2["new_this_run"] == 0
    assert sites2[0]["series"] == s["series"], "serie identique depuis le cache"

    # ── Nouveau granule : seul lui est traite ────────────────
    VALUES[NEW_FILE] = -13.4
    (gdir / NEW_FILE).write_bytes(b"x" * 16)
    calls.clear()
    sites3, source3 = update_swot.extract_sites_incremental(cfg)
    assert len(calls) == 1 and calls[0].endswith(NEW_FILE)
    assert source3["new_this_run"] == 1
    assert sites3[0]["latest"]["wse"] == -13.4
    assert sites3[0]["latest"]["date"].startswith("2025-07-14")
    assert sites3[0]["stats"]["n"] == 5

    # ── Changement de parametre : cache invalide ─────────────
    calls.clear()
    cfg_b3 = make_cfg(tmp, buffer_size=3)
    update_swot.extract_sites_incremental(cfg_b3)
    assert len(calls) == 7, "empreinte differente -> retraitement complet"

    # ── compute_since_date ───────────────────────────────────
    files = [str(gdir / n) for n in VALUES]
    since = update_swot.compute_since_date(files, 45, "2025-01-01")
    assert since == datetime(2025, 7, 14, 3, 15) - timedelta(days=45)
    assert update_swot.compute_since_date([], 45, "2025-01-01") == datetime(2025, 1, 1)

    # ── filter_new_granules ──────────────────────────────────
    class FakeGranule:
        def __init__(self, links):
            self._links = links
        def data_links(self):
            return self._links

    local = {"SWOT_A_20250101T000000.nc"}
    granules = [
        FakeGranule(["https://x/SWOT_A_20250101T000000.nc"]),      # deja local
        FakeGranule(["https://x/SWOT_B_20250201T000000.nc"]),      # nouveau
        FakeGranule(["https://x/readme.txt"]),                     # pas de .nc
    ]
    fresh = update_swot.filter_new_granules(granules, local)
    assert len(fresh) == 1 and fresh[0] is granules[1]

    # ── get_collections (short_names liste / chaine, short_name) ─
    assert update_swot.get_collections({"short_names": ["A", "B"]}) == ["A", "B"]
    assert update_swot.get_collections({"short_names": "A"}) == ["A"]
    assert update_swot.get_collections({"short_name": "X_2.0"}) == ["X_2.0"]

    # ── newest_remote_datetime ───────────────────────────────
    remote = update_swot.newest_remote_datetime([
        FakeGranule(["https://x/SWOT_A_20250101T000000.nc"]),
        FakeGranule(["https://x/SWOT_B_20260305T120000.nc",
                     "https://x/SWOT_B_20260305T120000.nc.md5"]),
        FakeGranule(["https://x/readme.txt"]),
    ])
    assert remote == datetime(2026, 3, 5, 12, 0, 0)

print("OK — extraction incrementale, filtres aval, fenetre de recherche "
      "et diff des granules valides.")
