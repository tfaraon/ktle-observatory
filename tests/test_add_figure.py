#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installation d'une photographie dans un emplacement (tools/add_figure.py).

Une photographie de telephone porte la position GPS et l'heure de prise
de vue : les publier serait indiscret. Ce test verifie que l'image
ecrite n'en garde rien, qu'elle est ramenee a une largeur raisonnable,
que le manifeste la declare avec son credit et perd sa note d'attente,
et qu'un emplacement inconnu est refuse.

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

    # Emplacement inconnu : refusé, avec la liste des emplacements connus
    try:
        af.add("inconnu", src, "x")
        raise AssertionError("un emplacement inconnu doit être refusé")
    except SystemExit as e:
        assert SLUG in str(e)

print("OK — image redimensionnée, métadonnées et position GPS retirées, manifeste complété "
      "avec le crédit, petites images intactes, emplacement inconnu refusé.")
