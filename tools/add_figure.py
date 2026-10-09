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

Plusieurs vues d'un meme sujet tiennent dans un seul emplacement. La
premiere s'installe normalement, les suivantes avec --add ; la page les
presente alors en panneaux lettres (a), (b), (c), chacun avec sa propre
legende si --caption en donne une :

    python tools/add_figure.py mound-spring blanche-cup-1.jpg \
        --credit "Photograph: Thomas Faraon" \
        --caption "Blanche Cup, the pool at the summit of the mound" \
        --figure-caption "Blanche Cup, one of the mound springs on the
                          arc from Lake Callabonna to Dalhousie."
    python tools/add_figure.py mound-spring blanche-cup-2.jpg --add \
        --caption "The tail of carbonate and reeds below the vent"

--figure-caption remplace la legende ecrite dans la page, sans qu'il
faille retoucher le constructeur ni relancer la construction.

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
MAX_PANELS = 3


def panel_files(entry):
    """Liste des images d'un emplacement, forme ancienne comprise.

    Un emplacement a longtemps porte une seule image sous « file ». La
    lire comme un premier panneau evite d'avoir a convertir les entrees
    existantes a la main.
    """
    if isinstance(entry.get("images"), list):
        return [dict(p) for p in entry["images"] if isinstance(p, dict) and p.get("file")]
    if entry.get("file"):
        return [{"file": entry["file"], "caption": entry.get("panel_caption", "")}]
    return []


def target_name(slug, index):
    """Nom de fichier d'un panneau : le premier garde le nom nu, pour
    ne pas renommer les images deja publiees."""
    return f"figures/{slug}.jpg" if index == 0 else f"figures/{slug}-{index + 1}.jpg"


def add(slug, source, credit, licence=None, url=None, max_width=MAX_WIDTH,
        write=True, caption=None, figure_caption=None, append=False):
    slots = fs.scan()
    if slug not in slots:
        raise SystemExit(f"Emplacement inconnu : {slug}\n"
                         f"Connus : {', '.join(sorted(slots))}")
    data = fs.manifest()
    entry = data["figures"].setdefault(slug, {})
    panels = panel_files(entry) if append else []
    if append and not panels:
        raise SystemExit(
            f"« {slug} » n'a pas encore d'image : installez la première "
            "sans --add.")
    if not credit and not entry.get("credit"):
        raise SystemExit(f"« {slug} » n'a pas de crédit : donnez --credit.")
    if len(panels) >= MAX_PANELS:
        raise SystemExit(
            f"« {slug} » a déjà {len(panels)} images, le maximum. "
            "Remplacez-en une (sans --add, elle écrase la première) ou "
            "choisissez un autre emplacement.")

    im = Image.open(source)
    im = im.convert("RGB")
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)),
                       Image.LANCZOS)

    index = len(panels)
    rel = target_name(slug, index)
    dest = fs.FRONTEND / "img" / rel
    if not write:
        return im, dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Sans exif= : ni GPS, ni date, ni modele d'appareil
    im.save(dest, "JPEG", quality=85, optimize=True)

    panels.append({"file": rel, "caption": caption or ""})
    entry.pop("note", None)
    entry.pop("panel_caption", None)
    if len(panels) == 1:
        # Un seul panneau : on garde la forme simple, lisible a l'oeil
        entry["file"] = panels[0]["file"]
        entry.pop("images", None)
        if panels[0]["caption"]:
            entry["panel_caption"] = panels[0]["caption"]
    else:
        entry["images"] = panels
        entry.pop("file", None)
    # Le credit vaut pour l'emplacement : une vue ajoutee n'a pas a le
    # repeter, et ne doit surtout pas l'effacer.
    if credit:
        entry["credit"] = credit
    if licence:
        entry["licence"] = licence
    if url:
        entry["url"] = url
    if figure_caption:
        entry["caption"] = " ".join(figure_caption.split())
    fs.MANIFEST.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return im, dest


def main():
    ap = argparse.ArgumentParser(
        description="Installe une image dans un emplacement du site")
    ap.add_argument("slug", nargs="?", help="emplacement, par exemple samphire")
    ap.add_argument("source", nargs="?", help="fichier image à installer")
    ap.add_argument("--credit", help="crédit affiché sous la légende")
    ap.add_argument("--licence", help="licence, si l'image n'est pas de vous")
    ap.add_argument("--url", help="lien vers la source, s'il y en a un")
    ap.add_argument("--caption", help="légende de CETTE image, affichée "
                                      "sous son panneau")
    ap.add_argument("--figure-caption", help="remplace la légende de la "
                                             "figure écrite dans la page")
    ap.add_argument("--add", action="store_true",
                    help="ajoute une vue à un emplacement qui a déjà une "
                         f"image (jusqu'à {MAX_PANELS})")
    ap.add_argument("--list", action="store_true", help="lister les emplacements")
    args = ap.parse_args()
    if args.list or not args.slug:
        fs.main()
        return
    if not args.source:
        raise SystemExit("Il faut un fichier : "
                         "python tools/add_figure.py <slug> <fichier> "
                         "--credit \"…\"")
    credit = args.credit
    if not credit and args.add:
        # Le credit d'un emplacement vaut pour toutes ses vues
        credit = fs.manifest()["figures"].get(args.slug, {}).get("credit")
    if not credit:
        raise SystemExit("Il faut un crédit : --credit \"Photograph: …\"")

    im, dest = add(args.slug, args.source, credit, args.licence, args.url,
                   caption=args.caption, figure_caption=args.figure_caption,
                   append=args.add)
    entry = fs.manifest()["figures"][args.slug]
    n = len(panel_files(entry))
    print(f"{args.slug} : {im.width}x{im.height} écrit dans {dest}, "
          "sans métadonnées")
    print(f"Crédit : {credit}   ({n} vue(s) dans cet emplacement)")
    if n > 1:
        print("La page les présentera en panneaux lettrés (a), (b), (c).")
    if args.figure_caption:
        print("Légende de la figure remplacée.")
    print("Publier avec  ./update.sh  (ou ./deploy/publish.sh)")


if __name__ == "__main__":
    main()
