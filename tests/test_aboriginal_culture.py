#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrite de la page Peoples de la partie Aboriginal Culture
(frontend/aboriginal_culture.js).

Une page qui nomme des nations et leurs droits doit etre exacte et
sourcee. Ces controles verifient que chaque renvoi aboutit a une
reference, que la page affiche sa reconnaissance du pays et sa regle de
conduite (ni ceremonie, ni site sacre, ni recit), et que ses ancres ne
se melangent pas a celles de la partie Natural History.

Execution :  python tests/test_aboriginal_culture.py
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name, var):
    src = (ROOT / "frontend" / name).read_text(encoding="utf-8")
    m = re.search(rf"const {var} = (\".*\");\s*$", src, re.S)
    assert m, f"{var} introuvable"
    return json.loads(m.group(1))


page = load("aboriginal_culture.js", "ABORIGINAL_CULTURE_HTML")
nh = load("natural_history.js", "NATURAL_HISTORY_HTML")

# ── Renvois et références ────────────────────────────────────
cited = re.findall(r'href="#acref-([a-z0-9]+)"', page)
listed = re.findall(r'id="acref-([a-z0-9]+)"', page)
assert cited and len(listed) == len(set(listed))
assert not set(cited) - set(listed), sorted(set(cited) - set(listed))
assert not set(listed) - set(cited), sorted(set(listed) - set(cited))

# ── Contenu attendu ──────────────────────────────────────────
for nation in ("Arabana", "Dieri", "Dhirari", "Wangkangurru", "Kuyani"):
    assert f"<b>{nation}" in page, f"{nation} absent du tableau"
rows = re.findall(r"<tr><td>", page)
assert len(rows) == 5, f"{len(rows)} lignes au lieu de 5"
qld = re.findall(r"<li>([A-Z][^<]*)</li>", page)
assert len(qld) == 16, f"{len(qld)} nations du Queensland au lieu de 16"
assert "71 Aboriginal language groups" in page
assert "Aboriginal Way" in page

# ── Reconnaissance et règle de conduite ──────────────────────
assert "Traditional Owners" in page and "nh-acknowledgement" in page
assert "does not describe ceremony, sacred places or stories" in page
assert "not intended for land claims" in page

# ── Style : pas de tiret comme ponctuation dans la prose ─────
for para in re.findall(r"<p>(.*?)</p>", page, re.S):
    text = html.unescape(re.sub(r"<[^>]+>", "", para))
    assert "\u2014" not in text and " \u2013 " not in text and " - " not in text, text[:80]

# ── Pas de collision d'ancres avec Natural History ───────────
ids_here = set(re.findall(r'id="([^"]+)"', page))
ids_nh = set(re.findall(r'id="([^"]+)"', nh))
assert not ids_here & ids_nh, sorted(ids_here & ids_nh)
assert all(i.startswith(("ac-", "acref-")) for i in ids_here), ids_here

# ── Liens externes sûrs ──────────────────────────────────────
for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', page):
    assert 'rel="noopener"' in tag, tag

print(f"OK — {len(set(cited))} références toutes citées, 5 nations autour du "
      f"lac, {len(qld)} nations du Queensland, règle de conduite et "
      "reconnaissance présentes, aucune collision d'ancres.")
