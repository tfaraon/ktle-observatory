#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coherence de l'adresse publique du site (tools/set_site_url.py).

L'adresse figure dans la citation recommandee de la page Data and
citation. Une divergence entre les fichiers n'a donc pas pour symptome
un affichage casse, mais une reference publiee qui renvoie vers une
adresse morte, ce qui ne se decouvre que bien plus tard et ne se repare
plus. Le test verifie que config.yaml fait seule autorite, et que
l'outil sait basculer d'une adresse a l'autre sans rien oublier.

Execution :  python tests/test_site_url.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import set_site_url as ssu  # noqa: E402

# ── L'adresse declaree, et toutes celles qui sont ecrites ────
url = ssu.configured()
assert url, "site.url absent de config.yaml"
assert url.startswith("https://"), url
assert url.endswith("/"), "l'adresse se termine par une barre, pour que "\
                          "« {url}img/share.jpg » reste correct"

for rel, _, hits in ssu.found():
    assert hits, f"{rel} : aucune adresse trouvée, le motif ne colle plus"
    for h in hits:
        assert h.startswith(url), f"{rel} porte {h}, config.yaml dit {url}"

# L'ancienne adresse ne doit plus trainer dans les fichiers propages
for rel, _, _ in ssu.found():
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "tfaraon.github.io" not in text, \
        f"{rel} : ancienne adresse GitHub Pages encore présente"

# ── La citation porte bien l'adresse ─────────────────────────
html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
cite = re.search(r'<p class="cite-block">(.*?)</p>', html, re.S)
assert cite, "bloc de citation introuvable"
assert url in cite.group(1), "la citation ne porte pas l'adresse du site"
assert "accessed" in cite.group(1)

# ── Bascule complete dans une copie jetable ──────────────────
with tempfile.TemporaryDirectory() as td:
    work = Path(td) / "repo"
    work.mkdir()
    for rel in ["config.yaml", "update.sh"]:
        shutil.copy(ROOT / rel, work / rel)
    for sub in ("frontend", "deploy"):
        (work / sub).mkdir()
    shutil.copy(ROOT / "frontend" / "index.html", work / "frontend")
    shutil.copy(ROOT / "deploy" / "local.env.example", work / "deploy")

    ssu.ROOT, ssu.CONFIG = work, work / "config.yaml"
    new = "https://exemple.test/"
    ssu.set_config(new)
    ssu.apply(new)
    assert ssu.configured() == new
    for rel, _, hits in ssu.found():
        for h in hits:
            assert h.startswith(new), (rel, h)
    # L'image de partage garde son chemin
    page = (work / "frontend" / "index.html").read_text(encoding="utf-8")
    assert f'content="{new}img/share.jpg"' in page, "chemin de l'image perdu"
    # Une barre finale en trop ne doit pas produire « //img »
    ssu.set_config("https://autre.test")
    ssu.apply(ssu.configured())
    page = (work / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "https://autre.test/img/share.jpg" in page, page[:0] or "double barre"
    # Deux bascules de suite n'empilent rien
    assert len(re.findall(r"https?://", page)) == \
        len(re.findall(r"https?://", html)), "occurrences dupliquées"

    ssu.ROOT, ssu.CONFIG = ROOT, ROOT / "config.yaml"

# ── Une adresse non chiffree est refusee ─────────────────────
r = subprocess.run([sys.executable, str(ROOT / "tools" / "set_site_url.py"),
                    "--set", "http://exemple.org/"],
                   capture_output=True, text=True)
assert r.returncode != 0 and "https://" in (r.stdout + r.stderr), r

print(f"OK — {url} déclarée dans config.yaml et propagée aux cinq "
      "emplacements, citation comprise, bascule et refus du http vérifiés.")
