#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventaire des emplacements de figures du site.

    python tools/figure_slots.py

Parcourt les pages construites et les pages ecrites a la main, et dit
pour chaque emplacement s'il a son image ou ce qu'il attend. Sert aussi
au test tests/test_figures.py.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MANIFEST = FRONTEND / "figures.json"
BUILT = {"natural_history": "NATURAL_HISTORY_HTML", "floods": "FLOODS_HTML",
         "rain_to_lake": "RAIN_TO_LAKE_HTML", "catchment": "CATCHMENT_HTML",
         "fauna_flora": "FAUNA_FLORA_HTML"}
HANDWRITTEN = {"index.html": "index.html", "methods.js": "methods.js"}
SLOT = re.compile(r'<figure class="fig" data-fig="([a-z0-9-]+)"><figcaption>(.*?)</figcaption>', re.S)


def scan():
    """{slug: {"page": nom, "caption": texte}}, dans l'ordre des pages."""
    out = {}
    for name, var in BUILT.items():
        src = (FRONTEND / f"{name}.js").read_text(encoding="utf-8")
        page = json.loads(re.search(rf"const {var} = (\".*\");\s*$", src, re.S).group(1))
        if "{fig:" in page:
            raise SystemExit(f"Marqueur de figure non rendu dans {name}.js")
        for slug, caption in SLOT.findall(page):
            out[slug] = {"page": f"{name}.js", "caption": clean(caption)}
    for label, name in HANDWRITTEN.items():
        text = (FRONTEND / name).read_text(encoding="utf-8")
        for slug, caption in SLOT.findall(re.sub(r"\s+", " ", text)):
            out[slug] = {"page": label, "caption": clean(caption)}
    return out


def clean(caption):
    return html.unescape(re.sub(r"<[^>]+>", "", caption)).strip()


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main():
    figs = manifest()["figures"]
    slots = scan()
    ready = 0
    for slug, info in slots.items():
        entry = figs.get(slug, {})
        if entry.get("file") and (FRONTEND / "img" / entry["file"]).exists():
            state, detail = "image", entry.get("credit", "")
            ready += 1
        else:
            state, detail = "à fournir", entry.get("note", "")
        print(f"{slug:<28} {state:<10} {info['page']:<20} {detail[:44]}")
    print(f"\n{ready} image(s) sur {len(slots)} emplacements.")
    unused = sorted(set(figs) - set(slots))
    if unused:
        print("Déclarés mais inutilisés :", ", ".join(unused))
    print("Pour en ajouter une :  python tools/add_figure.py <slug> <fichier> --credit \"…\"")


if __name__ == "__main__":
    main()
