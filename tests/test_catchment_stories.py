#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrite des parties Catchment et Stories.

Pour Stories, ce test verrouille la regle convenue : seuls figurent des
recits rendus publics par leurs detenteurs, en lien, jamais reformules.
Chaque lien de recit doit donc pointer vers une source tenue par les
detenteurs ou publiee par eux (projet Deep Time de l'ABC, maisons
d'edition, catalogue de la bibliotheque d'Etat), et aucun recueil de
missionnaire ou d'anthropologue ne doit y apparaitre.

Execution :  python tests/test_catchment_stories.py
"""

import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def load(name, var):
    src = (ROOT / "frontend" / name).read_text(encoding="utf-8")
    m = re.search(rf"const {var} = (\".*\");\s*$", src, re.S)
    assert m, f"{var} introuvable"
    return json.loads(m.group(1))


def check_page(page, ref_prefix, sec_prefix):
    cited = set(re.findall(rf'href="#{ref_prefix}([a-z0-9]+)"', page))
    listed = re.findall(rf'id="{ref_prefix}([a-z0-9]+)"', page)
    assert cited and len(listed) == len(set(listed))
    assert cited == set(listed), (cited ^ set(listed))
    for i in re.findall(r'id="([^"]+)"', page):
        assert i.startswith((sec_prefix, ref_prefix)), i
    for para in re.findall(r"<p>(.*?)</p>", page, re.S):
        text = html.unescape(re.sub(r"<[^>]+>", "", para))
        assert "\u2014" not in text and " \u2013 " not in text and " - " not in text, text[:80]
    for tag in re.findall(r'<a [^>]*target="_blank"[^>]*>', page):
        assert 'rel="noopener"' in tag, tag
    return len(cited)


catchment = load("catchment.js", "CATCHMENT_HTML")
stories = load("stories.js", "STORIES_HTML")
n_ct = check_page(catchment, "ctref-", "ct-")
n_st = check_page(stories, "stref-", "st-")

# ── Catchment : la carte et les faits clés ───────────────────
assert 'id="ct-map"' in catchment
for fact in ("1.2 million square kilometres", "Coongie Lakes", "Intergovernmental Agreement",
             "814&nbsp;GL"):
    assert fact in catchment, fact

# ── Stories : la règle, les sources, les exclusions ──────────
assert "links to them rather than retelling them" in stories
assert "names and images of people who have died" in stories
ALLOWED = ("www.abc.net.au", "www.uqp.com.au", "insidestory.org.au",
           "www.catalog.slsa.sa.gov.au", "github.com")
story_links = re.findall(r'<ul class="story-list">(.*?)</ul>', stories, re.S)
assert story_links, "aucune liste de récits"
hosts = {urlparse(u).hostname for block in story_links
         for u in re.findall(r'href="([^"]+)"', block)}
assert hosts <= set(ALLOWED), hosts - set(ALLOWED)
# Seules les listes de récits comptent : la page de présentation du projet,
# citée pour son protocole ICIP, n'est pas un récit.
deeptime = [u for block in story_links
            for u in re.findall(r'href="(https://www\.abc\.net\.au/news/deeptime/[^"]+)"', block)]
assert len(deeptime) == 3, deeptime
assert all("arabana-aboriginal-corporation" in u for u in deeptime), deeptime
for outsider in ("Reuther", "Howitt", "Gason", "Siebert", "Spencer and Gillen"):
    assert outsider not in stories, f"recueil extérieur cité : {outsider}"

# ── Les quatre pages de lecture n'ont aucune ancre commune ──
ids = []
for f, v in (("natural_history.js", "NATURAL_HISTORY_HTML"),
             ("aboriginal_culture.js", "ABORIGINAL_CULTURE_HTML"),
             ("catchment.js", "CATCHMENT_HTML"), ("stories.js", "STORIES_HTML"),
             ("fauna_flora.js", "FAUNA_FLORA_HTML")):
    ids += re.findall(r'id="([^"]+)"', load(f, v))
dups = {i for i in ids if ids.count(i) > 1}
assert not dups, dups

print(f"OK — Catchment : {n_ct} références citées, carte et faits clés ; "
      f"Stories : {n_st} références, liens vers {len(hosts)} sources de détenteurs, "
      "aucun recueil extérieur ; aucune ancre commune aux quatre pages.")
