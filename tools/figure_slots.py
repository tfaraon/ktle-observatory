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
BUILT = {"natural_history": "NATURAL_HISTORY_HTML", "lake_page": "LAKE_HTML",
         "country": "COUNTRY_HTML", "floods": "FLOODS_HTML",
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


def views(entry):
    """Images d'un emplacement : « images » (plusieurs vues) ou « file ».

    Meme lecture que tools/add_figure.py, redite ici pour que
    l'inventaire n'impose pas d'importer l'installateur, qui depend de
    Pillow.
    """
    if isinstance(entry.get("images"), list):
        return [p["file"] for p in entry["images"]
                if isinstance(p, dict) and p.get("file")]
    return [entry["file"]] if entry.get("file") else []


def adopt(write=True):
    """Declare dans le manifeste les images deja presentes sur le disque.

    Le manifeste et les images vivent separement : les fichiers sont dans
    frontend/img/figures/, leur declaration dans frontend/figures.json.
    Une restauration, une fusion malheureuse ou une archive deballee
    par-dessus peuvent donc effacer les declarations en laissant les
    images, et la page affiche alors un cadre « Image to come » devant
    une image qui existe. Cette fonction repare ce cas sans rien
    retelecharger : elle adopte tout fichier dont le nom correspond a un
    emplacement connu.
    """
    import json

    data = manifest()
    figs = data["figures"]
    slots = scan()
    folder = FRONTEND / "img" / "figures"
    adopted = []
    for path in sorted(folder.glob("*.jpg")) if folder.exists() else []:
        slug = path.stem
        if slug not in slots or slug not in figs:
            continue
        entry = figs[slug]
        if views(entry):
            continue
        entry["file"] = f"figures/{path.name}"
        entry.pop("note", None)
        adopted.append(slug)
    if adopted and write:
        MANIFEST.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    return adopted


def main():
    import sys
    if "--adopt" in sys.argv:
        got = adopt()
        if got:
            print(f"{len(got)} image(s) adoptée(s) : {', '.join(got)}")
            # Un credit vide fait echouer tests/test_figures.py, ce qui
            # est voulu : personne ne doit publier une image sans dire
            # d'ou elle vient, et deviner le credit serait pire.
            figs = manifest()["figures"]
            muettes = [g for g in got if not figs[g].get("credit")]
            if muettes:
                print(f"Sans crédit, à renseigner dans frontend/figures.json "
                      f"avant publication : {', '.join(muettes)}")
            print("Publier ensuite avec  ./update.sh")
        else:
            print("Aucune image sur le disque qui ne soit déjà déclarée.")
        return
    figs = manifest()["figures"]
    slots = scan()
    ready = 0
    for slug, info in slots.items():
        entry = figs.get(slug, {})
        have = [f for f in views(entry) if (FRONTEND / "img" / f).exists()]
        if have:
            state = "image" if len(have) == 1 else f"{len(have)} vues"
            detail = entry.get("credit", "")
            ready += 1
        else:
            state, detail = "à fournir", entry.get("note", "")
        print(f"{slug:<28} {state:<10} {info['page']:<20} {detail[:44]}")
    print(f"\n{ready} emplacement(s) illustré(s) sur {len(slots)}.")
    unused = sorted(set(figs) - set(slots))
    if unused:
        print("Déclarés mais inutilisés :", ", ".join(unused))
    print("Pour en ajouter une :  python tools/add_figure.py <slug> <fichier> --credit \"…\"")


if __name__ == "__main__":
    main()
