#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrite de la partie Natural History (frontend/natural_history.js).

Un texte de synthese ne vaut que par ses sources. Ces controles
verifient que chaque renvoi aboutit a une reference, que chaque
reference est effectivement citee, que la reconnaissance du pays
arabana est presente, et que la prose respecte la regle de style du
projet : aucun tiret comme ponctuation.

Execution :  python tests/test_natural_history.py
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "frontend" / "natural_history.js").read_text(encoding="utf-8")

m = re.search(r"const NATURAL_HISTORY_HTML = (\".*\");\s*$", src, re.S)
assert m, "NATURAL_HISTORY_HTML introuvable"
page = json.loads(m.group(1))

# ── Renvois et références ────────────────────────────────────
cited = re.findall(r'href="#ref-([a-z0-9]+)"', page)
listed = re.findall(r'id="ref-([a-z0-9]+)"', page)
assert cited, "aucune citation"
assert len(listed) == len(set(listed)), "référence en double"
orphans = sorted(set(cited) - set(listed))
assert not orphans, f"renvois sans référence : {orphans}"
uncited = sorted(set(listed) - set(cited))
assert not uncited, f"références jamais citées : {uncited}"

# ── Sommaire : chaque entrée mène à une section ──────────────
toc = re.findall(r'<li><a href="#(nh-[a-z-]+)">', page)
sections = set(re.findall(r'<section class="nh-section" id="(nh-[a-z-]+)"', page))
assert toc and set(toc) <= sections, (toc, sections)
assert "nh-references" in sections

# ── Reconnaissance du pays ───────────────────────────────────
assert "Arabana" in page and "Traditional Owners" in page
assert "nh-acknowledgement" in page

# ── Style : pas de tiret comme ponctuation dans la prose ─────
prose = re.findall(r'<section class="nh-section" id="nh-(?!references)[a-z-]+">(.*?)</section>',
                   page, re.S)
assert prose, "sections de texte introuvables"
for block in prose:
    text = html.unescape(re.sub(r"<[^>]+>", "", block))
    assert "\u2014" not in text, "tiret cadratin dans la prose"
    assert " \u2013 " not in text and " - " not in text, \
        "tiret espacé utilisé comme ponctuation"

# ── Liens externes sûrs ──────────────────────────────────────
for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', page):
    assert 'rel="noopener"' in tag, tag

words = len(re.sub(r"<[^>]+>", " ", "".join(prose)).split())
print(f"OK — {len(set(cited))} références toutes citées, {len(cited)} renvois "
      f"valides, {len(toc)} entrées de sommaire, {words} mots sans tiret de "
      "ponctuation, reconnaissance du pays présente.")
