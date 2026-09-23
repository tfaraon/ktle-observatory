#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telechargement des figures satellite (tools/fetch_figures.py), sans reseau.

Ce qui est verifie : chaque emplacement prevu existe dans le manifeste,
les requetes visent la bonne emprise et la bonne date, le script recule
d'un jour quand la scene manque, et le manifeste n'annonce une image
qu'une fois le fichier ecrit.

Execution :  python tests/test_fetch_figures.py
"""

import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import fetch_figures as ff  # noqa: E402

manifest = json.loads((ROOT / "frontend" / "figures.json").read_text(encoding="utf-8"))["figures"]
for slug in ff.PLANNED:
    assert slug in manifest, f"{slug} prévu mais absent de figures.json"
    assert not manifest[slug].get("file"), f"{slug} ne doit annoncer son fichier qu'une fois téléchargé"

asked = []


def fake(url, timeout=90):
    asked.append(url)
    if "2025-05-21" in url:              # cette scène manque, celle de la veille existe
        raise OSError("500")
    buf = io.BytesIO()
    Image.new("RGB", (1400, 764), (180, 140, 90)).save(buf, "JPEG")
    return buf.getvalue()


im, day = ff.grab("flood-2025-lake", get=fake, write=False)
assert str(day) == "2025-05-20", day
assert len(asked) == 2, "un jour essayé, puis le précédent"
assert "MODIS_Terra_CorrectedReflectance_Bands721" in asked[0]
assert "135.1" in asked[0] and "139.5" in asked[0], "emprise du lac"

asked.clear()
ff.grab("flood-2025-channel-country", get=fake, write=False)
assert "145.0" in asked[0], "emprise de la Channel Country"

print(f"OK — {len(ff.PLANNED)} emplacements satellite déclarés sans fichier tant qu'ils manquent, "
      "emprises et dates correctes, repli sur la veille.")
