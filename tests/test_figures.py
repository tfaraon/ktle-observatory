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
qu'une image annoncee existe bien avec son credit. Un emplacement
peut porter plusieurs vues du meme sujet : le test verifie alors qu'elles
existent toutes et qu'elles sont legendees de facon homogene.

Execution :  python tests/test_figures.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import figure_slots as fs  # noqa: E402
import add_figure as af  # noqa: E402

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
    panels = af.panel_files(entry)
    if panels:
        assert len(panels) <= af.MAX_PANELS, \
            f"{slug} : {len(panels)} vues, plus que {af.MAX_PANELS}"
        for p in panels:
            f = fs.FRONTEND / "img" / p["file"]
            assert f.exists(), (f"{slug} annonce {p['file']}, absent du disque : "
                                "lancer tools/fetch_figures.py, ou retirer "
                                "« file » du manifeste")
        assert entry.get("credit"), f"{slug} : une image publiée doit porter son crédit"
        # Une vue sans légende propre est admise, mais pas un panneau
        # muet au milieu de panneaux légendés : le lecteur croirait à un
        # oubli.
        own = [bool(p.get("caption")) for p in panels]
        if len(panels) > 1:
            assert all(own) or not any(own), \
                f"{slug} : légender toutes les vues, ou aucune"
        assert not entry.get("images") or not entry.get("file"), \
            f"{slug} : « file » et « images » à la fois"
    else:
        assert entry.get("note"), f"{slug} : indiquer ce qui est attendu dans « note »"

# Une légende de remplacement doit valoir celle de la page
for slug, entry in figs.items():
    if entry.get("caption"):
        assert len(entry["caption"].split()) >= 8, \
            f"{slug} : légende de remplacement trop courte"
        assert "\u2014" not in entry["caption"], entry["caption"]

ready = sum(1 for e in figs.values() if af.panel_files(e))
views = sum(len(af.panel_files(e)) for e in figs.values())
print(f"OK — {len(slots)} emplacements dans les pages, tous déclarés et légendés, "
      f"aucune déclaration orpheline, {ready} emplacement(s) illustré(s) "
      f"pour {views} vue(s).")
