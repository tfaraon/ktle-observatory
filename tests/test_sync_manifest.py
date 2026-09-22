#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la synchronisation du manifeste (pipeline/sync_manifest.py).

Le site publie apparie les scenarios dans le navigateur, avec les
reglages embarques dans site/manifest.json. Sans synchronisation, un
nouveau decalage de datum resterait sans effet en ligne : serveur local
et site publie choisiraient des scenarios differents.

Execution :  python tests/test_sync_manifest.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from export_static import matching_config  # noqa: E402
from sync_manifest import sync  # noqa: E402

# Manifeste publié avant le calage : décalage nul, arrondi au plus proche
old_manifest = {
    "bounds": [[-29.1, 136.9], [-27.8, 137.8]],
    "scales": {"currents": [0, 0.5]},
    "layers": ["currents", "hsign"],
    "matching": {"wlvl_offset": 0.0, "wlvl_rounding": "nearest",
                 "weights": {}, "normalize": "range"},
    "datum_label": "WSE (m, EGM2008 geoid)",
}
cfg = {"scenarios": {"wlvl_offset": 0.42, "wlvl_rounding": "down",
                     "weights": {"wlvl": 2.0}, "normalize": "range",
                     "wlvl_site": "Belt Bay"},
       "display": {"datum_label": "WSE (m, AHD)"}}

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "manifest.json"
    path.write_text(json.dumps(old_manifest), encoding="utf-8")

    changed = sync(cfg, path)
    new = json.loads(path.read_text(encoding="utf-8"))

    # Les réglages d'appariement suivent config.yaml
    assert new["matching"]["wlvl_offset"] == 0.42
    assert new["matching"]["wlvl_rounding"] == "down"
    assert new["matching"]["weights"] == {"wlvl": 2.0}
    assert new["datum_label"] == "WSE (m, AHD)"
    assert "wlvl_offset" in changed and changed["wlvl_offset"] == (0.0, 0.42)

    # Tout le reste est préservé à l'identique
    for key in ("bounds", "scales", "layers"):
        assert new[key] == old_manifest[key], key

    # Identique à ce qu'écrirait l'export complet
    assert new["matching"] == matching_config(cfg)

    # Un second passage ne change plus rien
    assert sync(cfg, path) == {}

print("OK — décalage et arrondi propagés au manifeste, le reste préservé, "
      "résultat identique à l'export complet.")
