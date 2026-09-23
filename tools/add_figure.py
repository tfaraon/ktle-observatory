#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installe une image dans un emplacement du site.

    python tools/add_figure.py samphire ~/Photos/samphire.jpg \
        --credit "Photograph: Thomas Faraon"

L'image est redimensionnee (1600 px de large au plus), reenregistree
sans aucune metadonnee et deposee dans frontend/img/figures/, puis
inscrite dans frontend/figures.json. Le retrait des metadonnees n'est
pas un detail : les photographies de telephone portent la position GPS
et l'heure de prise de vue, qui n'ont pas a etre publiees.

    python tools/add_figure.py --list      # les emplacements et leur etat
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import figure_slots as fs  # noqa: E402

MAX_WIDTH = 1600


def add(slug, source, credit, licence=None, url=None, max_width=MAX_WIDTH, write=True):
    slots = fs.scan()
    if slug not in slots:
        raise SystemExit(f"Emplacement inconnu : {slug}\n"
                         f"Connus : {', '.join(sorted(slots))}")
    im = Image.open(source)
    im = im.convert("RGB")
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.LANCZOS)
    dest = fs.FRONTEND / "img" / "figures" / f"{slug}.jpg"
    if write:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Sans exif= : ni GPS, ni date, ni modele d'appareil
        im.save(dest, "JPEG", quality=85, optimize=True)
        data = fs.manifest()
        entry = data["figures"].setdefault(slug, {})
        entry.pop("note", None)
        entry["file"] = f"figures/{slug}.jpg"
        entry["credit"] = credit
        if licence:
            entry["licence"] = licence
        if url:
            entry["url"] = url
        fs.MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return im, dest


def main():
    ap = argparse.ArgumentParser(description="Installe une image dans un emplacement du site")
    ap.add_argument("slug", nargs="?", help="emplacement, par exemple samphire")
    ap.add_argument("source", nargs="?", help="fichier image à installer")
    ap.add_argument("--credit", help="crédit affiché sous la légende")
    ap.add_argument("--licence", help="licence, si l'image n'est pas de vous")
    ap.add_argument("--url", help="lien vers la source, s'il y en a un")
    ap.add_argument("--list", action="store_true", help="lister les emplacements")
    args = ap.parse_args()
    if args.list or not args.slug:
        fs.main()
        return
    if not args.source or not args.credit:
        raise SystemExit("Il faut un fichier et un crédit : "
                         "python tools/add_figure.py <slug> <fichier> --credit \"…\"")
    im, dest = add(args.slug, args.source, args.credit, args.licence, args.url)
    print(f"{args.slug} : {im.width}x{im.height} écrit dans {dest}, sans métadonnées")
    print("Crédit :", args.credit)
    print("Publier avec  ./update.sh  (ou ./deploy/publish.sh)")


if __name__ == "__main__":
    main()
