#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emplacements de figures du site.

Les figures des livres et des articles cites sont protegees : le site ne
les reproduit pas. Chaque page reserve donc des emplacements, remplis
par frontend/figures.json, qui restent des cadres nommes tant que
l'image manque.

Ce test verifie que chaque emplacement des pages est declare, qu'aucun
marqueur n'est reste brut, que les legendes sont completes et sans tiret
de ponctuation, qu'aucune declaration ne traine sans emplacement, et
qu'une image annoncee existe bien avec son credit.

Execution :  python tests/test_figures.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import figure_slots as fs  # noqa: E402

slots = fs.scan()
figs = fs.manifest()["figures"]

assert len(slots) >= 20, f"seulement {len(slots)} emplacements"
for slug, info in slots.items():
    assert slug in figs, f"{slug} ({info['page']}) absent de figures.json"
    caption = info["caption"]
    assert len(caption.split()) >= 8, f"légende trop courte pour {slug} : {caption}"
    assert "\u2014" not in caption and " \u2013 " not in caption, caption

orphans = sorted(set(figs) - set(slots))
assert not orphans, f"déclarés sans emplacement : {orphans}"

for slug, entry in figs.items():
    if entry.get("file"):
        f = fs.FRONTEND / "img" / entry["file"]
        assert f.exists(), (f"{slug} annonce {entry['file']}, absent du disque : "
                            "lancer tools/fetch_figures.py, ou retirer « file » du manifeste")
        assert entry.get("credit"), f"{slug} : une image publiée doit porter son crédit"
    else:
        assert entry.get("note"), f"{slug} : indiquer ce qui est attendu dans « note »"

ready = sum(1 for e in figs.values() if e.get("file"))
print(f"OK — {len(slots)} emplacements dans les pages, tous déclarés et légendés, "
      f"aucune déclaration orpheline, {ready} image(s) en place.")
