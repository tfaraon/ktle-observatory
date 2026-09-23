#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image d'apercu des partages (tools/make_share_image.py), sans reseau.

Ce qui est verifie : les dimensions exigees par les reseaux sociaux
(1200 x 630), le recadrage d'une image plus large sans deformation, le
bandeau de titre en bas, le repli sur les jours precedents quand
l'imagerie du jour n'est pas publiee, et l'arret propre si rien n'est
disponible.

Execution :  python tests/test_share_image.py
"""

import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_share_image as msi  # noqa: E402

asked = []


def fake(url, timeout=60):
    asked.append(url)
    if "2026-09-20" not in url:          # seuls les jours plus anciens sont publiés
        raise OSError("404")
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1300), (196, 150, 96)).save(buf, "JPEG")
    return buf.getvalue()


im, day = msi.build("2026-09-22", get=fake, write=False)
assert im.size == (1200, 630), im.size
assert str(day) == "2026-09-20", day
assert len(asked) == 3, "deux jours essayés avant celui qui existe"
assert "MODIS_Terra_CorrectedReflectance_Bands721" in asked[0]
assert "TIME=2026-09-22" in asked[0].replace("%3A", ":")

# Bandeau : le bas de l'image est sombre, le haut garde l'imagerie
top = im.crop((0, 0, 1200, 400)).resize((1, 1)).getpixel((0, 0))
band = im.crop((0, 520, 1200, 630)).resize((1, 1)).getpixel((0, 0))
assert sum(band) < sum(top), (band, top)
assert band[2] >= band[0], "bandeau dans le bleu profond du site"

# Aucune image disponible : arrêt explicite
def dead(url, timeout=60):
    raise OSError("réseau coupé")


try:
    msi.build("2026-09-22", get=dead, write=False)
    raise AssertionError("un échec total doit arrêter le script")
except SystemExit as e:
    assert "MODIS" in str(e)

print("OK — 1200x630, recadrage sans déformation, bandeau de titre, repli sur les jours "
      "précédents, arrêt explicite si rien n'est disponible.")
