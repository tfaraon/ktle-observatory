#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page Research group : identifiants ORCID et rendu (tools/build_group.py).

L'enjeu n'est pas l'affichage mais l'exactitude. Un ORCID dont un
chiffre est faux reste un identifiant bien forme : il ne casse rien, il
renvoie vers le dossier de quelqu'un d'autre et attribue ce travail a un
tiers. La clef de controle est donc verifiee ici sur des identifiants
publies par ORCID et sur des fautes de frappe realistes.

Le test verifie aussi qu'aucun identifiant n'est invente : une personne
sans ORCID communique ne doit porter aucun lien.

Execution :  python tests/test_group.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_group as bg  # noqa: E402

checks = []


def check(label, cond, detail=""):
    checks.append((label, cond))
    print(("  OK   " if cond else "  ECHEC") + f" {label} "
          + (str(detail) if not cond else ""))


# ── Clef de controle ────────────────────────────────────────
# Identifiants d'exemple publies par ORCID, dont un a clef « X ».
for good in ("0000-0002-1825-0097", "0000-0001-5109-3700",
             "0000-0002-1694-233X"):
    check(f"ORCID valide accepté {good}", bg.orcid_valid(good))

# Fautes de frappe : dernier chiffre, chiffre interne, longueur, format
for bad in ("0000-0002-1825-0098", "0000-0002-1825-0197",
            "0000-0002-1825-009", "000-0002-1825-0097",
            "0000000218250097", "0000-0002-1825-00X7",
            "0000-0002-1694-2330"):
    check(f"ORCID fautif refusé {bad}", not bg.orcid_valid(bad))

# ── Rien d'invente ──────────────────────────────────────────
page = bg.render()
for p in bg.PEOPLE:
    if p["orcid"] is None:
        check(f"aucun lien ORCID pour {p['name']}",
              p["name"] in page and "orcid.org" not in page.split(
                  p["name"])[1].split("</li>")[0])

check("cinq personnes", len(bg.PEOPLE) == 5, len(bg.PEOPLE))
check("chaque personne a au moins une affiliation",
      all(p["affiliations"] for p in bg.PEOPLE))
check("aucun rôle supposé",
      all(p["role"] in (None, "PhD student") for p in bg.PEOPLE),
      [p["role"] for p in bg.PEOPLE])

# Le fichier genere est bien a jour par rapport au script
built = (ROOT / "frontend" / "group.js").read_text(encoding="utf-8")
check("group.js régénéré depuis le script",
      page in built.replace("\\\"", "\"").replace("\\n", "\n")
      or page.replace('"', '\\"') in built)
check("group.js ne porte aucun orcid.org non vérifié",
      built.count("orcid.org") == sum(1 for p in bg.PEOPLE if p["orcid"]))

# ── Un ORCID fautif doit faire echouer la construction ──────
saved = bg.PEOPLE[0]["orcid"]
bg.PEOPLE[0]["orcid"] = "0000-0002-1825-0098"
try:
    bg.render()
    check("construction refusée sur un ORCID fautif", False, "aucune sortie")
except SystemExit as e:
    check("construction refusée sur un ORCID fautif",
          "clef de contrôle" in str(e) or "contrôle" in str(e), e)
finally:
    bg.PEOPLE[0]["orcid"] = saved

# ── Cablage dans la page ────────────────────────────────────
html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
check("group.js chargé par index.html", 'src="group.js"' in html)
check("panneau tab-group présent", 'id="tab-group"' in html)
check("onglet Research group dans la barre",
      'data-tab="group"' in html)
app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
check("onglet rattaché à une partie",
      re.search(r"group:\s*\"[a-z-]+\"", app) is not None)
check("contenu injecté à la première ouverture",
      "GROUP_HTML" in app)

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} vérifications réussies")
raise SystemExit(1 if failed else 0)
