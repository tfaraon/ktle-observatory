#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modifie la legende d'une figure deja en place.

Une legende existe a deux endroits. Celle ecrite dans la page vient du
marqueur {fig:slug|…} du constructeur : la changer demande de relancer
la construction de la page. Celle de frontend/figures.json, sous la cle
« caption », la remplace a l'affichage ; c'est celle que ce script
ecrit, et elle n'exige aucune reconstruction.

    python tools/set_caption.py                      # toutes les figures
    python tools/set_caption.py mound-spring         # l'etat d'une figure
    python tools/set_caption.py mound-spring --figure "Blanche Cup, …"
    python tools/set_caption.py mound-spring --panel b "Le talus de …"
    python tools/set_caption.py mound-spring --reset  # revenir a la page

Editer figures.json a la main fait la meme chose. Ce script sert a ne
pas casser le JSON et a verifier au passage ce que les tests exigent :
une legende d'au moins huit mots, et pas de tiret cadratin.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import figure_slots as fs  # noqa: E402

MIN_WORDS = 8          # legende de figure : une phrase
MIN_PANEL_WORDS = 3    # legende de vue : un membre de phrase suffit
LETTERS = "abc"


def check(text, min_words=MIN_WORDS):
    """Refus explicite plutot qu'un test rouge une heure plus tard.

    Le minimum differe : la legende de la figure porte la phrase que
    tests/test_figures.py exige, celle d'une vue dit seulement ce qu'on
    y voit (« le talus de carbonate sous la source »).
    """
    words = len(text.split())
    if words < min_words:
        raise SystemExit(
            f"Légende trop courte ({words} mots, {min_words} au minimum) : "
            + ("les figures du site portent une phrase, pas une étiquette."
               if min_words == MIN_WORDS else
               "dites ce que montre la vue."))
    if "—" in text or " – " in text:
        raise SystemExit("Pas de tiret cadratin dans une légende : "
                         "utilisez une virgule, un deux-points ou un point.")
    return " ".join(text.split())


def panels_of(entry):
    if isinstance(entry.get("images"), list):
        return [p for p in entry["images"]
                if isinstance(p, dict) and p.get("file")]
    if entry.get("file"):
        return [{"file": entry["file"], "caption": entry.get("panel_caption", "")}]
    return []


def show(slug, slots, figs):
    info = slots[slug]
    entry = figs.get(slug, {})
    panels = panels_of(entry)
    print(f"\n{slug}   ({info['page']}, {len(panels)} vue(s))")
    print(f"  page      : {info['caption']}")
    if entry.get("caption"):
        print(f"  remplacée : {entry['caption']}")
        print("              (c'est celle que le site affiche)")
    else:
        print("  remplacée : aucune, le site affiche celle de la page")
    for i, p in enumerate(panels):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        print(f"  ({letter})      : {p.get('caption') or '— sans légende —'}")


def write(data):
    fs.MANIFEST.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Modifie la légende d'une figure déjà en place")
    ap.add_argument("slug", nargs="?", help="emplacement, par exemple mound-spring")
    ap.add_argument("--figure", metavar="TEXTE",
                    help="légende de la figure, qui remplace celle de la page")
    ap.add_argument("--panel", nargs=2, metavar=("LETTRE", "TEXTE"),
                    action="append", default=[],
                    help="légende d'une vue : --panel b \"…\" (répétable)")
    ap.add_argument("--reset", action="store_true",
                    help="retire la légende de remplacement")
    args = ap.parse_args()

    slots = fs.scan()
    data = fs.manifest()
    figs = data["figures"]

    if not args.slug:
        for slug in slots:
            show(slug, slots, figs)
        print("\nPour en changer une :  python tools/set_caption.py <slug> "
              "--figure \"…\"")
        return

    if args.slug not in slots:
        raise SystemExit(f"Emplacement inconnu : {args.slug}\n"
                         f"Connus : {', '.join(sorted(slots))}")
    entry = figs.setdefault(args.slug, {})
    panels = panels_of(entry)

    if not (args.figure or args.panel or args.reset):
        show(args.slug, slots, figs)
        return

    changed = []
    if args.reset:
        if entry.pop("caption", None) is None:
            print("Aucune légende de remplacement : rien à retirer.")
        else:
            changed.append("légende de la figure revenue à celle de la page")
    if args.figure:
        entry["caption"] = check(args.figure)
        changed.append("légende de la figure remplacée")
    for letter, text in args.panel:
        key = letter.strip().lower().strip("()")
        index = LETTERS.index(key) if key in LETTERS else None
        if index is None and key.isdigit():
            index = int(key) - 1
        if index is None or not 0 <= index < len(panels):
            raise SystemExit(
                f"Vue « {letter} » inconnue : cet emplacement en a "
                f"{len(panels)} "
                f"({', '.join(LETTERS[:len(panels)]) or 'aucune'}).")
        panels[index]["caption"] = check(text, MIN_PANEL_WORDS)
        changed.append(f"légende de la vue ({LETTERS[index]}) remplacée")

    # Reecrire la forme qui correspond au nombre de vues
    if args.panel:
        if len(panels) == 1:
            entry["panel_caption"] = panels[0]["caption"]
        else:
            entry["images"] = panels

    write(data)
    for line in changed:
        print(line.capitalize())
    show(args.slug, slots, fs.manifest()["figures"])

    muets = [LETTERS[i] for i, p in enumerate(panels) if not p.get("caption")]
    if len(panels) > 1 and muets and len(muets) < len(panels):
        print(f"\nAttention : la ou les vues ({', '.join(muets)}) n'ont pas "
              "de légende.\nUn panneau muet au milieu de panneaux légendés "
              "se lit comme un oubli ;\ntests/test_figures.py le refuse.")
    print("\nPublier avec  ./update.sh")


if __name__ == "__main__":
    main()
