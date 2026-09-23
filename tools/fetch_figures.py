#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Images satellite des figures du site -> frontend/img/figures/

Les figures des livres et des articles cites sont protegees par le droit
d'auteur et ne peuvent pas etre republiees ici. L'imagerie de la NASA,
elle, est libre avec attribution : ce script la telecharge pour les
emplacements que frontend/figures.json declare, aux dates qui illustrent
chaque propos.

    python tools/fetch_figures.py             # les images manquantes
    python tools/fetch_figures.py --all       # toutes, meme deja presentes
    python tools/fetch_figures.py --list      # ce qui est prevu

Les emplacements sans image ici (photographies de terrain, figures d'un
article) restent des cadres vides sur le site, avec le nom du fichier
attendu : deposer le fichier dans frontend/img/figures/ suffit a le
remplir.
"""

import argparse
import io
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "frontend" / "img" / "figures"
MANIFEST = ROOT / "frontend" / "figures.json"
GIBS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
SWIR = "MODIS_Terra_CorrectedReflectance_Bands721"

LAKE = (135.1, -29.9, 139.5, -27.5)              # le lac et ses abords
CHANNEL = (138.0, -28.5, 145.0, -22.0)           # la Channel Country

# slug : (date, emprise, largeur en pixels)
PLANNED = {
    "lake-from-space": ("2025-07-08", LAKE, 1400),          # le lac plein, apres la crue
    "flood-2025-lake": ("2025-05-21", LAKE, 1400),          # la premiere vague sur le lit
    "flood-2025-channel-country": ("2025-04-10", CHANNEL, 1500),
    "flood-2011-lake": ("2011-05-15", LAKE, 1400),
    "dry-lake": ("2024-09-15", LAKE, 1400),                 # la croute de sel, sans eau
    "channel-country-dry": ("2024-09-15", CHANNEL, 1500),
}


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "ktle-observatory/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def image_url(day, bbox, width):
    height = int(round(width * (bbox[3] - bbox[1]) / (bbox[2] - bbox[0])))
    q = urllib.parse.urlencode({
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1",
        "LAYERS": SWIR, "STYLES": "", "SRS": "EPSG:4326",
        "BBOX": ",".join(str(v) for v in bbox), "WIDTH": str(width), "HEIGHT": str(height),
        "FORMAT": "image/jpeg", "TIME": str(day),
    })
    return f"{GIBS}?{q}"


def grab(slug, get=fetch, write=True):
    """Image d'un emplacement, en reculant d'un jour si la scene manque."""
    day, bbox, width = PLANNED[slug]
    start = date.fromisoformat(day)
    errors = []
    for back in range(0, 6):
        d = start - timedelta(days=back)
        try:
            raw = get(image_url(d, bbox, width))
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            errors.append(f"{d}: {type(e).__name__}")
            continue
        if write:
            FIG_DIR.mkdir(parents=True, exist_ok=True)
            im.save(FIG_DIR / f"{slug}.jpg", quality=84, optimize=True)
        return im, d
    raise RuntimeError(f"{slug} : aucune image ({'; '.join(errors[:3])})")


def update_manifest(done):
    """Date de la scene dans le manifeste, pour que la legende puisse la citer."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for slug, day in done.items():
        entry = data["figures"].setdefault(slug, {})
        entry["file"] = f"figures/{slug}.jpg"
        entry["date"] = str(day)
        entry.setdefault("credit", "NASA Worldview, MODIS Terra")
        entry.setdefault("licence", "Open, with attribution to NASA")
        entry.setdefault("url", "https://worldview.earthdata.nasa.gov/")
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Images satellite des figures du site")
    ap.add_argument("--all", action="store_true", help="Retélécharger même les images présentes")
    ap.add_argument("--list", action="store_true", help="Lister ce qui est prévu")
    args = ap.parse_args()
    if args.list:
        for slug, (day, bbox, width) in PLANNED.items():
            here = "présente" if (FIG_DIR / f"{slug}.jpg").exists() else "manquante"
            print(f"{slug:<28} {day}  {width} px  {here}")
        return
    done, failed = {}, []
    for slug in PLANNED:
        if not args.all and (FIG_DIR / f"{slug}.jpg").exists():
            continue
        try:
            im, day = grab(slug)
            done[slug] = day
            print(f"{slug} : {im.width}x{im.height}, scène du {day}")
        except Exception as e:
            failed.append(str(e))
    if done:
        update_manifest(done)
    for f in failed:
        print("échec :", f)
    print(f"{len(done)} image(s) écrite(s) dans {FIG_DIR}")
    print("Les emplacements sans image restent des cadres, avec le nom du fichier attendu.")


if __name__ == "__main__":
    main()
