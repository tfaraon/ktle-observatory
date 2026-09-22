#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du cache de bathymetrie (hypsometry.load_bathymetry).

La bathymetrie est reconstituee depuis une sortie WAVE stockee sur le
disque externe des simulations. Elle ne change jamais : la relire a
chaque execution rendait les calculs d'etendue et le calage SWIR
dependants d'un disque qui n'est pas toujours monte.

Execution :  python tests/test_bathymetry_cache.py
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import hypsometry as hyp  # noqa: E402

MISSING = "/Volumes/disque_absent/Output/wave/wave_x.nc"

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "data").mkdir()

    def write_index(key, path=MISSING):
        (root / "data" / "scenarios.json").write_text(json.dumps({
            "demo": False,
            "scenarios": [{"key": key, "files": {"wave": path},
                           "params": {"wlvl": -10.0}}],
        }), encoding="utf-8")

    hyp.ROOT = root
    cache = root / "data" / "bathymetry.npz"

    # 1. Disque absent et pas de cache : message explicite, pas de trace
    write_index("scen-A")
    try:
        hyp.load_bathymetry(cache)
        raise AssertionError("une erreur était attendue")
    except SystemExit as e:
        msg = str(e)
        assert "introuvable" in msg, msg
        assert "disque_absent" in msg and "monté" in msg, msg

    # 2. Cache présent et lié au bon scénario : aucun accès au disque
    bed = np.array([[-15.0, -14.0], [np.nan, -12.0]])
    areas = np.full((2, 2), 250000.0)
    xv = np.array([[1.0, 2.0], [1.0, 2.0]])
    yv = np.array([[5.0, 5.0], [6.0, 6.0]])
    np.savez_compressed(cache, bed=bed, areas=areas, xv=xv, yv=yv,
                        source=np.array("scen-A"))

    got = hyp.load_bathymetry(cache)
    assert got["cached"] is True
    assert got["source"] == "scen-A"
    assert np.array_equal(got["bed"], bed, equal_nan=True)
    assert np.array_equal(got["areas"], areas)
    assert np.array_equal(got["xv"], xv) and np.array_equal(got["yv"], yv)

    # 3. L'index désigne un autre fichier : le cache est périmé et doit
    #    être reconstruit, ce qui exige à nouveau le disque
    write_index("scen-B")
    try:
        hyp.load_bathymetry(cache)
        raise AssertionError("un cache périmé ne doit pas être servi")
    except SystemExit as e:
        assert "introuvable" in str(e)

    # 4. refresh force la relecture même avec un cache valide
    write_index("scen-A")
    try:
        hyp.load_bathymetry(cache, refresh=True)
        raise AssertionError("refresh doit ignorer le cache")
    except SystemExit:
        pass

print("OK — cache servi sans disque, périmé quand la source change, "
      "message explicite si le disque manque.")
