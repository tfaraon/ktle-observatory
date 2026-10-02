#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrite des trois pages tirees de la source Natural History :
frontend/lake_page.js, natural_history.js et country.js.

Un texte de synthese ne vaut que par ses sources. Ces controles
verifient, pour chaque page, que tout renvoi aboutit a une reference,
que toute reference listee est citee, que les identifiants ne se
chevauchent pas d'une page a l'autre (les trois peuvent etre dans la
page en meme temps), que la reconnaissance du pays arabana est
presente, et que la prose n'utilise aucun tiret comme ponctuation.

Execution :  python tests/test_natural_history.py
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = {"lake_page.js": ("LAKE_HTML", "lkref-"),
         "natural_history.js": ("NATURAL_HISTORY_HTML", "nhref-"),
         "country.js": ("COUNTRY_HTML", "cpref-")}

all_ids, total_cited, total_words, total_toc = set(), 0, 0, 0
for name, (var, prefix) in PAGES.items():
    src = (ROOT / "frontend" / name).read_text(encoding="utf-8")
    m = re.search(rf"const {var} = (\".*\");\s*$", src, re.S)
    assert m, f"{var} introuvable dans {name}"
    page = json.loads(m.group(1))

    cited = re.findall(rf'href="#{prefix}([a-z0-9]+)"', page)
    listed = re.findall(rf'id="{prefix}([a-z0-9]+)"', page)
    assert cited, f"{name} : aucune citation"
    assert len(listed) == len(set(listed)), f"{name} : référence en double"
    assert not set(cited) - set(listed), f"{name} : renvois sans référence"
    assert not set(listed) - set(cited), f"{name} : références jamais citées"
    ids = {prefix + k for k in listed}
    assert not (ids & all_ids), f"{name} : identifiants partagés avec une autre page"
    all_ids |= ids
    total_cited += len(set(cited))

    toc = re.findall(r'<li><a href="#([a-z-]+)">', page)
    sections = set(re.findall(r'<section class="nh-section" id="([a-z-]+)"', page))
    assert toc and set(toc) <= sections, (name, toc, sections)
    total_toc += len(toc)

    assert "Arabana" in page and "Traditional Owners" in page, name
    assert "nh-acknowledgement" in page, name

    prose = re.findall(r'<section class="nh-section" id="nh-[a-z-]+">(.*?)</section>', page, re.S)
    assert prose, f"{name} : sections de texte introuvables"
    for block in prose:
        text = html.unescape(re.sub(r"<[^>]+>", "", block))
        assert "\u2014" not in text, f"{name} : tiret cadratin dans la prose"
        assert " \u2013 " not in text and " - " not in text, \
            f"{name} : tiret espacé utilisé comme ponctuation"
    for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', page):
        assert 'rel="noopener"' in tag, tag
    total_words += len(re.sub(r"<[^>]+>", " ", "".join(prose)).split())

print(f"OK — {len(PAGES)} pages, {total_cited} références toutes citées, identifiants distincts "
      f"d'une page à l'autre, {total_toc} entrées de sommaire, {total_words} mots sans tiret de "
      "ponctuation, reconnaissance du pays présente.")
