#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image d'apercu pour les partages -> frontend/img/share.jpg (1200 x 630)

Quand le site est partage sur un reseau social ou dans un courriel, c'est
cette image qui s'affiche. Elle est composee a partir de la meme imagerie
MODIS que la page d'accueil, prise sur le jour le plus recent disponible,
avec un bandeau portant le titre.

    python tools/make_share_image.py
    python tools/make_share_image.py --date 2025-07-08
"""

import argparse
import io
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "img" / "share.jpg"
GIBS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
BBOX = (135.1, -29.9, 139.5, -27.5)          # le lac et ses abords, comme l'accueil
SIZE = (1200, 630)
TITLE = "Kati Thanda\u2013Lake Eyre Observatory"
SUBTITLE = "Satellite measurements, hydrodynamic models and natural history"
FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",       # macOS
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",    # Linux
         "/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "ktle-observatory/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def image_url(day):
    q = urllib.parse.urlencode({
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1",
        "LAYERS": "MODIS_Terra_CorrectedReflectance_Bands721", "STYLES": "",
        "SRS": "EPSG:4326", "BBOX": ",".join(str(v) for v in BBOX),
        "WIDTH": str(SIZE[0] * 2), "HEIGHT": str(int(SIZE[0] * 2 * (BBOX[3] - BBOX[1]) / (BBOX[2] - BBOX[0]))),
        "FORMAT": "image/jpeg", "TIME": str(day),
    })
    return f"{GIBS}?{q}"


def font(index, size):
    for path in FONTS[index:]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose(raw):
    """Image MODIS recadree en 1200 x 630, avec le bandeau de titre."""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    ratio = max(SIZE[0] / im.width, SIZE[1] / im.height)
    im = im.resize((max(SIZE[0], int(im.width * ratio)), max(SIZE[1], int(im.height * ratio))))
    left = (im.width - SIZE[0]) // 2
    top = (im.height - SIZE[1]) // 2
    im = im.crop((left, top, left + SIZE[0], top + SIZE[1]))

    band = Image.new("RGBA", (SIZE[0], 150), (22, 51, 59, 216))
    im = im.convert("RGBA")
    im.alpha_composite(band, (0, SIZE[1] - 150))
    d = ImageDraw.Draw(im)
    d.text((56, SIZE[1] - 116), TITLE, font=font(0, 44), fill=(255, 255, 255))
    d.text((56, SIZE[1] - 60), SUBTITLE, font=font(2, 24), fill=(214, 226, 226))
    return im.convert("RGB")


def build(day=None, get=fetch, write=True):
    """Essaie le jour demande, puis les precedents : l'image du jour n'est pas encore publiee."""
    start = date.fromisoformat(day) if day else date.today() - timedelta(days=2)
    errors = []
    for back in range(0, 8):
        d = start - timedelta(days=back)
        try:
            raw = get(image_url(d))
        except Exception as e:
            errors.append(f"{d}: {type(e).__name__}")
            continue
        im = compose(raw)
        if write:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            im.save(OUT, quality=86, optimize=True)
        return im, d
    raise SystemExit("Aucune image MODIS disponible : " + "; ".join(errors[:3]))


def main():
    ap = argparse.ArgumentParser(description="Image d'aperçu pour les partages")
    ap.add_argument("--date", help="jour MODIS à utiliser (AAAA-MM-JJ)")
    args = ap.parse_args()
    im, day = build(args.date)
    print(f"Image écrite : {OUT} ({im.width}x{im.height}, MODIS du {day})")
    print("Elle est publiée sous site/img/share.jpg et référencée par les balises og:image.")


if __name__ == "__main__":
    main()
