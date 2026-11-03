#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Propage l'adresse publique du site dans les fichiers qui la portent.

L'adresse apparait a cinq endroits : les deux balises Open Graph et la
ligne de citation de frontend/index.html, la valeur par defaut de
update.sh, et le modele deploy/local.env.example. Les laisser diverger
n'a aucun symptome visible, sauf un : une citation publiee qui renvoie
vers une adresse morte. La source unique est donc site.url dans
config.yaml, et ce script la recopie partout.

    python tools/set_site_url.py                       # etat actuel
    python tools/set_site_url.py --set https://exemple.org/
    python tools/set_site_url.py --apply               # applique config.yaml

tests/test_site_url.py verifie ensuite que plus rien ne diverge.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.yaml"

# Chaque emplacement : fichier, motif, et reconstruction de la ligne.
# Le motif capture l'adresse pour pouvoir la remplacer sans toucher au
# reste de la ligne, qui porte du balisage ou des guillemets.
URL_RE = r"https?://[^\s\"'<>)]+"
PLACES = [
    ("frontend/index.html",
     rf'(<meta property="og:url" content=")({URL_RE})(">)',
     "{url}"),
    ("frontend/index.html",
     rf'(<meta property="og:image" content=")({URL_RE})(">)',
     "{url}img/share.jpg"),
    ("frontend/index.html",
     rf"(<p class=\"cite-block\">.*?\.\s*\n\s*)({URL_RE})( \(accessed)",
     "{url}"),
    ("update.sh",
     rf'(SITE_URL="\$\{{SITE_URL:-)({URL_RE})(\}}")',
     "{url}"),
    ("deploy/local.env.example",
     rf"(SITE_URL=)({URL_RE})(\s*$)",
     "{url}"),
]


def configured():
    """Adresse declaree dans config.yaml, terminee par une barre."""
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    url = ((cfg.get("site") or {}).get("url") or "").strip()
    return url.rstrip("/") + "/" if url else ""


def found():
    """Adresses actuellement ecrites, par emplacement."""
    out = []
    for rel, pattern, _ in PLACES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        hits = re.findall(pattern, text, re.S | re.M)
        out.append((rel, pattern, [h[1] for h in hits]))
    return out


def apply(url, write=True):
    """Ecrit l'adresse partout. Retourne les emplacements modifies."""
    changed = []
    by_file = {}
    for rel, pattern, template in PLACES:
        text = by_file.get(rel)
        if text is None:
            text = (ROOT / rel).read_text(encoding="utf-8")
        new = template.format(url=url)
        text, n = re.subn(pattern, lambda m: m.group(1) + new + m.group(3),
                          text, flags=re.S | re.M)
        if n == 0:
            raise SystemExit(
                f"Emplacement introuvable dans {rel} : le fichier a changé "
                "de forme, corrigez PLACES dans tools/set_site_url.py.")
        by_file[rel] = text
        changed.append((rel, n))
    if write:
        for rel, text in by_file.items():
            (ROOT / rel).write_text(text, encoding="utf-8")
    return changed


def set_config(url):
    """Ecrit site.url dans config.yaml, en gardant les commentaires."""
    text = CONFIG.read_text(encoding="utf-8")
    block = ("# Adresse publique du site. Source unique : "
             "tools/set_site_url.py\n"
             "# la recopie dans index.html, update.sh et local.env.example.\n"
             "site:\n"
             f'  url: "{url}"\n')
    if re.search(r"^site:\s*$", text, re.M):
        text = re.sub(r'^(site:\s*\n\s+url:\s*")[^"]*(")',
                      lambda m: m.group(1) + url + m.group(2), text,
                      count=1, flags=re.M)
    else:
        # Avant « lake: », qui ouvre la description du site
        text = re.sub(r"^lake:", block + "\nlake:", text, count=1, flags=re.M)
    CONFIG.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Propage l'adresse publique du site")
    ap.add_argument("--set", metavar="URL",
                    help="nouvelle adresse, écrite dans config.yaml "
                         "puis propagée")
    ap.add_argument("--apply", action="store_true",
                    help="propage l'adresse déjà déclarée dans config.yaml")
    args = ap.parse_args()

    if args.set:
        url = args.set.strip()
        if not url.startswith("https://"):
            raise SystemExit("L'adresse doit commencer par https:// : un site "
                             "cité doit l'être sur une adresse chiffrée.")
        url = url.rstrip("/") + "/"
        set_config(url)
        for rel, n in apply(url):
            print(f"{rel} : {n} occurrence(s)")
        print(f"\nAdresse du site : {url}")
        print("Publier avec  ./update.sh")
        return

    if args.apply:
        url = configured()
        if not url:
            raise SystemExit("site.url absent de config.yaml : utilisez --set")
        for rel, n in apply(url):
            print(f"{rel} : {n} occurrence(s)")
        print(f"\nAdresse du site : {url}")
        return

    url = configured()
    print(f"config.yaml : {url or '(non déclarée)'}")
    for rel, _, hits in found():
        for h in hits:
            flag = "" if url and h.startswith(url.rstrip("/")) else "   ← diffère"
            print(f"  {rel:<28} {h}{flag}")
    print("\nPour en changer :  python tools/set_site_url.py --set "
          "https://exemple.org/")


if __name__ == "__main__":
    sys.exit(main())
