#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Structure de la page Plants and animals (frontend/fauna_flora.js).

La page est rangee par groupe, et chaque groupe porte un emplacement que
le site remplit en direct depuis iNaturalist, et depuis eBird pour les
oiseaux. Ce test verifie l'ordre des groupes, les references, et que
chaque emplacement designe des groupes qu'iNaturalist connait.

Execution :  python tests/test_fauna_flora.py
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "frontend" / "fauna_flora.js").read_text(encoding="utf-8")
page = json.loads(re.search(r"const FAUNA_FLORA_HTML = (\".*\");\s*$", src, re.S).group(1))

sections = re.findall(r'<section class="nh-section" id="(ff-[a-z]+)">', page)
assert sections == ["ff-plants", "ff-invertebrates", "ff-fish", "ff-frogs", "ff-reptiles",
                    "ff-birds", "ff-mammals", "ff-references"], sections

ICONIC = {"Plantae", "Insecta", "Arachnida", "Mollusca", "Animalia", "Actinopterygii",
          "Amphibia", "Reptilia", "Aves", "Mammalia"}
blocks = re.findall(r'<div class="obs-block" data-groups="([^"]+)" data-name="([a-z]+)"( data-ebird="true")?>', page)
assert len(blocks) == 7, blocks
for groups, name, ebird in blocks:
    assert set(groups.split(",")) <= ICONIC, groups
    assert bool(ebird) == (name == "birds"), "eBird n'alimente que les oiseaux"

cited = set(re.findall(r'href="#ffref-([a-z0-9]+)"', page))
listed = set(re.findall(r'id="ffref-([a-z0-9]+)"', page))
assert cited and cited == listed, cited ^ listed

# Aucune phrase ne renvoie a une section voisine qu'elle ne nomme pas
for para in re.findall(r"<p>(.*?)</p>", page, re.S):
    text = html.unescape(re.sub(r"<[^>]+>", "", para))
    assert not re.match(r"(Those|These) ", text), text[:60]
    assert "\u2014" not in text and " \u2013 " not in text, text[:60]

print(f"OK — {len(sections) - 1} groupes dans l'ordre, un emplacement d'observations par "
      f"groupe, eBird pour les seuls oiseaux, {len(cited)} références citées.")
