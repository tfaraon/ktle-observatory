#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installation d'une photographie dans un emplacement (tools/add_figure.py).

Une photographie de telephone porte la position GPS et l'heure de prise
de vue : les publier serait indiscret. Ce test verifie que l'image
ecrite n'en garde rien, qu'elle est ramenee a une largeur raisonnable,
que le manifeste la declare avec son credit et perd sa note d'attente,
et qu'un emplacement inconnu est refuse. Verifie aussi qu'un meme
emplacement accepte jusqu'a trois vues du meme sujet, chacune avec sa
legende, sans renommer la premiere ni perdre le credit.

Execution :  python tests/test_add_figure.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import add_figure as af  # noqa: E402
import figure_slots as fs  # noqa: E402

SLUG = "samphire"

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # Le manifeste et le dossier d'images sont copiés : le dépôt n'est pas touché
    work = td / "frontend"
    (work / "img" / "figures").mkdir(parents=True)
    shutil.copy(fs.MANIFEST, work / "figures.json")
    for name in list(fs.BUILT) + ["methods"]:
        shutil.copy(fs.FRONTEND / f"{name}.js", work / f"{name}.js")
    shutil.copy(fs.FRONTEND / "index.html", work / "index.html")
    fs.FRONTEND, fs.MANIFEST = work, work / "figures.json"

    # Une photographie avec des métadonnées, dont une position GPS
    src = td / "photo.jpg"
    exif = Image.Exif()
    exif[271] = "TestPhone"                     # marque de l'appareil
    exif[306] = "2026:09:23 08:15:00"           # date de prise de vue
    exif[34853] = {1: "S", 2: (28.0, 30.0, 0.0)}            # position GPS
    Image.new("RGB", (4000, 3000), (120, 150, 110)).save(src, exif=exif)
    assert Image.open(src).getexif(), "la photo de départ doit porter des métadonnées"

    im, dest = af.add(SLUG, src, "Photograph: Thomas Faraon")
    assert dest.exists() and dest.name == f"{SLUG}.jpg"
    assert im.width == 1600 and im.height == 1200, im.size

    out = Image.open(dest)
    assert not out.getexif(), "métadonnées (dont GPS) retirées"
    assert 34853 not in out.getexif()

    entry = json.loads((work / "figures.json").read_text(encoding="utf-8"))["figures"][SLUG]
    assert entry["file"] == f"figures/{SLUG}.jpg"
    assert entry["credit"] == "Photograph: Thomas Faraon"
    assert "note" not in entry, "la note d'attente disparaît une fois l'image en place"

    # Une image déjà petite n'est pas agrandie
    small = td / "small.jpg"
    Image.new("RGB", (800, 600), (90, 90, 90)).save(small)
    im2, _ = af.add("lake-eyre-dragon", small, "Photograph: Thomas Faraon")
    assert im2.size == (800, 600), im2.size

    # ── Trois vues d'un même sujet dans un seul emplacement ──
    # Cas de Blanche Cup : trois photographies du même mound spring, qui
    # doivent tenir dans l'emplacement « mound-spring » en panneaux
    # lettrés, chacune avec sa légende.
    views = []
    for i in range(3):
        v = td / f"blanche-{i}.jpg"
        Image.new("RGB", (2400, 1600), (100 + 10 * i, 120, 110)).save(v, exif=exif)
        views.append(v)

    af.add("mound-spring", views[0], "Photograph: Thomas Faraon",
           caption="The pool at the summit of the mound",
           figure_caption="Blanche Cup, one of the mound springs on the arc "
                          "that runs from Lake Callabonna to Dalhousie.")
    entry = fs.manifest()["figures"]["mound-spring"]
    # Une seule vue : forme simple conservée, pas de liste
    assert entry["file"] == "figures/mound-spring.jpg", entry
    assert "images" not in entry
    assert entry["caption"].startswith("Blanche Cup")

    af.add("mound-spring", views[1], None, caption="The carbonate tail below "
           "the vent", append=True)
    af.add("mound-spring", views[2], None, caption="Reeds around the outflow",
           append=True)
    entry = fs.manifest()["figures"]["mound-spring"]
    panels = af.panel_files(entry)
    assert [p["file"] for p in panels] == ["figures/mound-spring.jpg",
                                           "figures/mound-spring-2.jpg",
                                           "figures/mound-spring-3.jpg"], panels
    assert [p["caption"] for p in panels][1] == "The carbonate tail below the vent"
    assert "file" not in entry, "« file » et « images » ne coexistent pas"
    # La première image garde son nom : les liens déjà publiés restent bons
    for p in panels:
        f = work / "img" / p["file"]
        assert f.exists(), p
        assert not Image.open(f).getexif(), f"métadonnées restantes dans {p['file']}"
    # Le crédit de l'emplacement survit à un ajout sans --credit
    assert entry["credit"] == "Photograph: Thomas Faraon"
    # La légende de la figure n'est pas écrasée par un ajout
    assert entry["caption"].startswith("Blanche Cup")

    # Au-delà de trois, l'ajout est refusé plutôt que de produire une
    # grille illisible
    try:
        af.add("mound-spring", views[0], None, caption="x", append=True)
        raise AssertionError("un quatrième panneau doit être refusé")
    except SystemExit as e:
        assert "maximum" in str(e), e

    # --add sur un emplacement vide : refusé, avec la marche à suivre
    try:
        af.add("salt-crust", views[0], "Photograph: Thomas Faraon", append=True)
        raise AssertionError("--add sur un emplacement vide doit être refusé")
    except SystemExit as e:
        assert "sans --add" in str(e), e

    # Emplacement inconnu : refusé, avec la liste des emplacements connus
    try:
        af.add("inconnu", src, "x")
        raise AssertionError("un emplacement inconnu doit être refusé")
    except SystemExit as e:
        assert SLUG in str(e)

print("OK — image redimensionnée, métadonnées et position GPS retirées, manifeste complété "
      "avec le crédit, petites images intactes, trois vues légendées dans un seul "
      "emplacement, quatrième refusée, emplacement inconnu refusé.")
