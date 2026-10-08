#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du cache par journee de pipeline/lake_area.py.

Sans ce cache, chaque passage relit toute l'archive SWOT : la chaine ne
peut tourner que la ou les 761 granules sont montes. Le cache deplace
l'unite de calcul a la journee — la surface etant calculee sur la grille
fusionnee du jour, c'est la seule unite reutilisable — et permet
d'effacer un granule apres son premier passage.

Verifie :
  - 1er passage : tous les granules lus, cache ecrit ;
  - 2e passage : aucun granule relu, serie identique ;
  - granule nouveau : seul son jour est retraite ;
  - granule ajoute a un jour deja calcule : ce jour est recalcule ;
  - granules effaces : la serie survit, sans relecture ;
  - parametre change : cache invalide, tout retraite ;
  - --limit n'ecrit pas le cache ;
  - journee sans eau retenue memorisee, donc non relue ;
  - KTLE_SWOT_DIR l'emporte sur config.yaml.

Execution :  python tests/test_area_cache.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import lake_area as la          # noqa: E402
import update_swot              # noqa: E402

# Deux granules le meme jour, un autre jour, puis un jour sans eau.
GRANULES = {
    "SWOT_L2_HR_Raster_100m_UTM53H_x_001_A_20250310T031500_20250310T031510_PID0_01.nc": 120.0,
    "SWOT_L2_HR_Raster_100m_UTM53H_x_001_B_20250310T032000_20250310T032010_PID0_01.nc": 80.0,
    "SWOT_L2_HR_Raster_100m_UTM53H_x_002_A_20250331T031500_20250331T031510_PID0_01.nc": 300.0,
    "SWOT_L2_HR_Raster_100m_UTM53H_x_003_A_20250421T031500_20250421T031510_PID0_01.nc": 0.0,
}
NEW_DAY = ("SWOT_L2_HR_Raster_100m_UTM53H_x_004_A_20250512T031500"
           "_20250512T031510_PID0_01.nc")
SAME_DAY = ("SWOT_L2_HR_Raster_100m_UTM53H_x_001_C_20250310T032500"
            "_20250310T032510_PID0_01.nc")

read = []


def fake_read_granule(path, boundary=None, params=None, zone=None,
                      south=True, want_mask=False):
    """Stub : la surface depend du nom, pas du contenu du fichier."""
    read.append(os.path.basename(path))
    km2 = GRANULES.get(os.path.basename(path), 50.0)
    if km2 == 0.0:               # jour vu, mais hors de l'emprise du lac
        return {"area_m2": 0.0, "uncert_m2": None, "n_cells": 0,
                "covered_cells": 0}
    return {"area_m2": km2 * 1e6, "uncert_m2": km2 * 1e4,
            "n_cells": int(km2 * 100), "covered_cells": int(km2 * 100)}


la.read_granule = fake_read_granule


def make_cfg(tmp, median_size=5):
    return {
        "paths": {"swot_data": str(tmp / "granules")},
        "scenarios": {"utm_zone": 53, "southern_hemisphere": True},
        "area": {"boundary": "none", "workers": 1, "resolution": None,
                 "median_size": median_size},
    }


def write_granules(d, names):
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"stub")


def run(cfg, tmp, **kw):
    del read[:]
    return la.build(cfg, out_path=tmp / "lake_area.json",
                    cache_path=tmp / "area_cache.json", **kw)


def areas(payload):
    return {e["date"]: e["area_km2"] for e in payload["series"]}


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    gdir = tmp / "granules"
    write_granules(gdir, GRANULES)
    cfg = make_cfg(tmp)

    # ── 1er passage : tout est lu ────────────────────────────
    first = run(cfg, tmp)
    assert len(read) == 4, read
    assert areas(first) == {"2025-03-10": 200.0, "2025-03-31": 300.0}, \
        areas(first)
    cache = json.loads((tmp / "area_cache.json").read_text(encoding="utf-8"))
    assert sorted(cache["days"]) == ["2025-03-10", "2025-03-31", "2025-04-21"]
    # Le jour sans eau est memorise, sinon il serait relu indefiniment
    assert cache["days"]["2025-04-21"]["entry"] is None
    assert len(cache["days"]["2025-03-10"]["granules"]) == 2
    assert first["n_granules"] == 4

    # ── 2e passage : rien n'est relu, serie identique ────────
    second = run(cfg, tmp)
    assert read == [], read
    assert areas(second) == areas(first)
    assert second["n_granules"] == 4

    # ── Un jour nouveau : seul celui-la est traite ───────────
    write_granules(gdir, [NEW_DAY])
    third = run(cfg, tmp)
    assert read == [NEW_DAY], read
    assert areas(third)["2025-05-12"] == 50.0
    assert areas(third)["2025-03-10"] == 200.0

    # ── Un granule de plus sur un jour connu : ce jour repasse ──
    write_granules(gdir, [SAME_DAY])
    fourth = run(cfg, tmp)
    assert sorted(read) == sorted(
        [SAME_DAY] + [n for n in GRANULES if "20250310" in n]), read
    assert areas(fourth)["2025-03-10"] == 250.0      # 120 + 80 + 50
    assert areas(fourth)["2025-03-31"] == 300.0      # intact

    # ── Granules effaces : la serie tient toujours ───────────
    # C'est le cas de l'hebergement distant : le granule est telecharge,
    # lu, puis jete faute de place.
    for p in gdir.glob("*.nc"):
        p.unlink()
    fifth = run(cfg, tmp)
    assert read == [], read
    assert areas(fifth) == areas(fourth), (areas(fifth), areas(fourth))
    assert fifth["n_granules"] == 6

    # ── Parametre change : cache invalide ────────────────────
    write_granules(gdir, list(GRANULES) + [NEW_DAY, SAME_DAY])
    changed = run(make_cfg(tmp, median_size=3), tmp)
    assert len(read) == 6, read
    assert areas(changed)["2025-03-10"] == 250.0

    # ── --limit n'ecrit pas le cache ─────────────────────────
    before = (tmp / "area_cache.json").read_text(encoding="utf-8")
    partial = run(make_cfg(tmp, median_size=3), tmp, limit=1)
    assert (tmp / "area_cache.json").read_text(encoding="utf-8") == before
    # L'essai ne doit pas non plus reprendre le cache : sinon il ecrirait
    # une serie complete dont une journee est amputee.
    assert len(partial["series"]) == 1, partial["series"]

    # ── --rebuild-cache retraite tout ────────────────────────
    rebuilt = run(make_cfg(tmp, median_size=3), tmp, rebuild=True)
    assert len(read) == 6, read
    assert areas(rebuilt)["2025-03-10"] == 250.0

    # ── KTLE_SWOT_DIR l'emporte sur config.yaml ──────────────
    other = tmp / "ailleurs"
    other.mkdir()
    os.environ["KTLE_SWOT_DIR"] = str(other)
    try:
        assert update_swot.swot_dir(cfg) == other
        assert update_swot.download_dir(
            {"download": {"target_dir": "/nowhere"}}) == other
    finally:
        del os.environ["KTLE_SWOT_DIR"]
    assert update_swot.swot_dir(cfg) == gdir

print("OK — journées mises en cache, granules effaçables, cache invalidé "
      "sur changement de paramètre.")
