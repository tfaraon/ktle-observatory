#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modification d'une legende deja en place (tools/set_caption.py).

Une legende se change sans toucher a l'image ni relancer la
construction d'une page : c'est la cle « caption » de figures.json qui
l'emporte sur le texte ecrit dans la page. Ce test verifie que
l'ecriture est juste et que les refus protegent ce que les autres tests
exigent :

  - legende de figure posee, puis retiree pour revenir a celle de la page ;
  - legende d'une vue designee par sa lettre, les autres intactes ;
  - lettre inconnue, legende trop courte, tiret cadratin : refus ;
  - un emplacement a une seule vue garde la forme simple ;
  - le JSON reste valide et relisible par figure_slots.

Execution :  python tests/test_set_caption.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import figure_slots as fs  # noqa: E402

LEAD = ("Blanche Cup, one of the mound springs on the arc that runs from "
        "Lake Callabonna to Dalhousie.")
SHORT = "Blanche Cup"
DASHED = ("Blanche Cup, a mound spring of the Great Artesian Basin — one "
          "of many along the arc.")

with tempfile.TemporaryDirectory() as td:
    work = Path(td) / "frontend"
    work.mkdir(parents=True)
    (work / "img" / "figures").mkdir(parents=True)
    shutil.copy(fs.MANIFEST, work / "figures.json")
    for name in list(fs.BUILT) + ["methods"]:
        shutil.copy(fs.FRONTEND / f"{name}.js", work / f"{name}.js")
    shutil.copy(fs.FRONTEND / "index.html", work / "index.html")
    fs.FRONTEND, fs.MANIFEST = work, work / "figures.json"

    # Le module lit figure_slots : il doit etre importe apres le detournement
    import set_caption as sc  # noqa: E402
    sc.fs = fs

    data = fs.manifest()
    data["figures"]["mound-spring"] = {
        "credit": "Photograph: Thomas Faraon",
        "images": [
            {"file": "figures/mound-spring.jpg", "caption": "The pool at the summit"},
            {"file": "figures/mound-spring-2.jpg", "caption": "The carbonate tail"},
        ],
    }
    data["figures"]["goyder-channel"] = {
        "credit": "Photograph: Thomas Faraon",
        "file": "figures/goyder-channel.jpg",
    }
    fs.MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    slots = fs.scan()
    page_caption = slots["mound-spring"]["caption"]
    assert page_caption and "mound spring" in page_caption.lower()

    def run(argv):
        sys.argv = ["set_caption.py"] + argv
        sc.main()
        return fs.manifest()["figures"]

    # ── Légende de figure posée, puis retirée ────────────────
    figs = run(["mound-spring", "--figure", LEAD])
    assert figs["mound-spring"]["caption"] == LEAD, figs["mound-spring"]
    # La légende de la page n'est pas touchée : elle reste le défaut
    assert fs.scan()["mound-spring"]["caption"] == page_caption

    figs = run(["mound-spring", "--reset"])
    assert "caption" not in figs["mound-spring"], figs["mound-spring"]

    # ── Légende d'une vue, désignée par sa lettre ───────────
    figs = run(["mound-spring", "--panel", "b", "The carbonate tail below the vent"])
    panels = figs["mound-spring"]["images"]
    assert panels[1]["caption"] == "The carbonate tail below the vent", panels
    assert panels[0]["caption"] == "The pool at the summit", "vue (a) intacte"
    # Entre parenthèses ou par son numéro, même résultat
    figs = run(["mound-spring", "--panel", "(a)", "The pool at the summit of the mound"])
    assert figs["mound-spring"]["images"][0]["caption"].endswith("of the mound")
    figs = run(["mound-spring", "--panel", "2", "Reeds around the outflow below"])
    assert figs["mound-spring"]["images"][1]["caption"].startswith("Reeds")

    # ── Emplacement à une seule vue : forme simple gardée ───
    figs = run(["goyder-channel", "--panel", "a",
                "The narrow link between the two lakes"])
    assert figs["goyder-channel"]["file"] == "figures/goyder-channel.jpg"
    assert "images" not in figs["goyder-channel"], figs["goyder-channel"]
    assert figs["goyder-channel"]["panel_caption"].startswith("The narrow link")

    # ── Refus ───────────────────────────────────────────────
    for argv, expect in (
        (["mound-spring", "--panel", "c", "A third view that does not exist here"],
         "inconnue"),
        (["mound-spring", "--figure", SHORT], "trop courte"),
        (["mound-spring", "--figure", DASHED], "tiret"),
        (["inexistant", "--figure", LEAD], "inconnu"),
    ):
        try:
            run(argv)
            raise AssertionError(f"devait être refusé : {argv}")
        except SystemExit as e:
            assert expect in str(e), (argv, str(e))

    # Un refus n'écrit rien
    figs = fs.manifest()["figures"]
    assert "caption" not in figs["mound-spring"], "un refus ne doit rien écrire"

    # ── Le JSON reste valide et relisible ───────────────────
    again = json.loads(fs.MANIFEST.read_text(encoding="utf-8"))
    assert again["figures"]["mound-spring"]["images"][0]["caption"]
    assert fs.scan()["mound-spring"]["page"].endswith(".js")

print("OK — légende de figure posée et retirée, vues désignées par lettre ou "
      "numéro, forme simple préservée, légende trop courte, tiret cadratin et "
      "lettre inconnue refusés sans rien écrire.")
