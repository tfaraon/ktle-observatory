#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/group.js, onglet « Research group ».

Une page de personnes nommees, publiee sous leur nom et leur
institution. Deux garde-fous, pour cette raison :

  * un identifiant ORCID est verifie par sa clef de controle (ISO 7064
    MOD 11-2) avant d'etre ecrit. Un chiffre faux ne donne pas un lien
    mort : il donne un lien vers le dossier de quelqu'un d'autre, ce qui
    ne se voit pas a la relecture et attribue ce travail a un tiers.

  * un identifiant absent reste absent. Le script le signale a la fin et
    n'ecrit rien a sa place, plutot que d'inventer une valeur
    plausible : ORCID ne se devine pas.

Le role n'est ecrit que s'il a ete communique. Supposer « superviseur »
parce que la personne n'est pas doctorante serait une affirmation sur
une personne reelle, sur un site public.

    python tools/build_group.py
"""

import html
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "group.js"

# ── Institutions, sous leur nom propre en anglais ────────────
UNIMELB = "The University of Melbourne"
CNRS = "CNRS"
UNISTRA = "Université de Strasbourg"
TUDELFT = "Delft University of Technology"

INSTITUTIONS = [
    (UNIMELB, "School of Geography, Earth and Atmospheric Sciences",
     "https://www.unimelb.edu.au/"),
    (CNRS, "Centre national de la recherche scientifique",
     "https://www.cnrs.fr/en"),
    (UNISTRA, "Institut Terre et Environnement de Strasbourg",
     "https://en.unistra.fr/"),
    (TUDELFT, "Faculty of Civil Engineering and Geosciences",
     "https://www.tudelft.nl/en/"),
]

# ── Les personnes ───────────────────────────────────────────
# role=None : non communique, donc non ecrit.
# orcid=None : non communique, donc aucun lien. Jamais devine.
PEOPLE = [
    {
        "name": "Thomas Faraon",
        "role": "PhD student",
        "affiliations": [UNIMELB, CNRS],
        "orcid": None,
    },
    {
        "name": "Ahmed Naceur Mama",
        "role": "PhD student",
        "affiliations": [UNIMELB, CNRS],
        "orcid": None,
    },
    {
        "name": "Jan-Hendrik May",
        "role": None,
        "affiliations": [UNIMELB],
        "orcid": None,
    },
    {
        "name": "Mathieu Schuster",
        "role": None,
        "affiliations": [CNRS, UNISTRA],
        "orcid": None,
    },
    {
        "name": "Joep Storms",
        "role": None,
        "affiliations": [TUDELFT],
        "orcid": None,
    },
]

STANDFIRST = (
    "This observatory is built and maintained by a group working on the "
    "hydrology and sedimentology of Kati Thanda&nbsp;&ndash; Lake Eyre, "
    "across the University of Melbourne, the CNRS and the Université de "
    "Strasbourg, and Delft University of Technology. The site brings "
    "together the satellite measurements, the hydrodynamic scenarios and "
    "the methods behind both."
)

CONTACT = (
    "For questions about the measurements, the model or the data behind "
    "any figure on this site, write to the corresponding author listed on "
    'the <a href="#publications">Publications</a> page. Corrections to '
    "this page, and to anything else published here, are welcome."
)


def orcid_valid(value):
    """Clef de controle ORCID : ISO 7064 MOD 11-2 sur les 15 chiffres."""
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value):
        return False
    digits = value.replace("-", "")
    total = 0
    for c in digits[:15]:
        total = (total + int(c)) * 2
    check = (12 - total % 11) % 11
    return ("X" if check == 10 else str(check)) == digits[15]


def person_html(p):
    name = html.escape(p["name"])
    parts = [f'<li class="person">', f'<p class="person-name">{name}</p>']

    if p["role"]:
        parts.append(f'<p class="person-role">{html.escape(p["role"])}</p>')

    affs = "".join(f"<li>{html.escape(a)}</li>" for a in p["affiliations"])
    parts.append(f'<ul class="person-affiliations">{affs}</ul>')

    orcid = p["orcid"]
    if orcid:
        if not orcid_valid(orcid):
            sys.exit(f"ORCID refusé pour {p['name']} : {orcid} — la clef de "
                     "contrôle ne correspond pas. Un chiffre faux renvoie "
                     "vers le dossier d'une autre personne.")
        parts.append(
            f'<p class="person-orcid">'
            f'<a href="https://orcid.org/{orcid}" target="_blank" '
            f'rel="noopener"><span class="orcid-mark" aria-hidden="true"></span>'
            f'{orcid}</a></p>')

    parts.append("</li>")
    return "".join(parts)


def render():
    people_html = "".join(person_html(p) for p in PEOPLE)

    inst_html = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener">{html.escape(short)}</a>'
        f'<span class="inst-unit">{html.escape(unit)}</span></li>'
        for short, unit, url in INSTITUTIONS)

    return f"""<article class="panel group-page">
  <div class="panel-head">
    <p class="eyebrow">About</p>
    <h2>Research group</h2>
  </div>
  <div class="prose-body">
    <p class="lede">{STANDFIRST}</p>
    <ul class="people">{people_html}</ul>
    <h3>Institutions</h3>
    <ul class="institutions">{inst_html}</ul>
    <h3>Contact and corrections</h3>
    <p>{CONTACT}</p>
  </div>
</article>"""


def main():
    js = ("/* Onglet Research group, genere par tools/build_group.py.\n"
          " * Les personnes et leurs ORCID sont declares dans ce script ;\n"
          " * ne pas modifier group.js a la main. */\n"
          f"const GROUP_HTML = {json.dumps(render(), ensure_ascii=False)};\n")
    OUT.write_text(js, encoding="utf-8")

    missing = [p["name"] for p in PEOPLE if not p["orcid"]]
    no_role = [p["name"] for p in PEOPLE if not p["role"]]
    print(f"{OUT.name} : {len(PEOPLE)} personnes, "
          f"{len(PEOPLE) - len(missing)} ORCID écrits")
    if missing:
        print("  ORCID non communiqué, donc absent de la page : "
              + ", ".join(missing))
    if no_role:
        print("  rôle non communiqué, donc absent de la page : "
              + ", ".join(no_role))


if __name__ == "__main__":
    main()
