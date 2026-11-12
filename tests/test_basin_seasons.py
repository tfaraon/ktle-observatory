#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pluie saisonniere de longue periode (pipeline/basin_seasons.py), sans reseau.

Les pieges que ce test garde fermes :
  - la saison chaude mord sur l'annee civile suivante ; une erreur d'un
    mois decale un siecle de serie sans rien casser de visible ;
  - une moyenne en cache ne vaut que pour le masque qui l'a produite,
    donc changer de contour doit vider le cache et non melanger des
    nombres incomparables ;
  - la ponderation par le cosinus de la latitude doit vraiment peser ;
  - un mois pas encore publie (404) se saute, les autres erreurs se
    signalent ;
  - si les grilles mensuelles ne repondent pas, le script s'arrete sur
    un message, au lieu de se rabattre en silence sur les grilles
    quotidiennes, soit trente fois plus de fichiers ;
  - les annees incompletes restent marquees, et sortent des moyennes.

Execution :  python tests/test_basin_seasons.py
"""

import json
import sys
import tempfile
import urllib.error
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image, TiffImagePlugin, TiffTags

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import basin_outline as bo       # noqa: E402
import basin_seasons as bs       # noqa: E402

LON0, LAT0, STEP = 131.0, -18.0, 0.05
NX, NY = int((148.0 - LON0) / STEP), int((LAT0 + 33.0) / STEP)
lons = LON0 + STEP * (np.arange(NX) + 0.5)
lats = LAT0 - STEP * (np.arange(NY) + 0.5)


def write_geotiff(path, grid):
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[33550] = (STEP, STEP, 0.0)
    ifd.tagtype[33550] = TiffTags.DOUBLE
    ifd[33922] = (0.0, 0.0, 0.0, LON0, LAT0, 0.0)
    ifd.tagtype[33922] = TiffTags.DOUBLE
    ifd[42113] = "-32767"
    ifd.tagtype[42113] = TiffTags.ASCII
    Image.fromarray(grid.astype("float32"), "F").save(path, tiffinfo=ifd)


checks = []


def check(label, ok, detail=""):
    checks.append((label, bool(ok)))
    if not ok:
        print(f"ECHEC — {label}" + (f" : {detail}" if detail else ""))


# ── Decoupage des saisons ───────────────────────────────────────

warm = bs.season_months(1974, "warm")
check("saison chaude a cheval sur deux annees",
      warm == [(1974, 10), (1974, 11), (1974, 12), (1975, 1), (1975, 2), (1975, 3)],
      warm)
check("saison fraiche dans l'annee",
      bs.season_months(1974, "cool") == [(1974, m) for m in range(4, 10)])

# Un mois appartient a une seule saison, et les douze sont couverts
every = set(bs.WARM) | set(bs.COOL)
check("les douze mois sont couverts une fois",
      every == set(range(1, 13)) and not (set(bs.WARM) & set(bs.COOL)))


# ── Agregation, completude, moyennes ────────────────────────────

# Deux annees pleines a 10 mm par mois, puis une annee tronquee
months = {}
for y in (1990, 1991, 1992):
    for m in range(1, 13):
        months[f"{y}{m:02d}"] = 10.0
for m in (1, 2, 3):                     # debut 1993 : finit la saison chaude 1992
    months[f"1993{m:02d}"] = 10.0

rows = bs.aggregate(months, 1990, 1993)
by_year = {r["year"]: r for r in rows}
check("annee pleine : 60 mm par saison",
      by_year[1990]["warm_mm"] == 60.0 and by_year[1990]["cool_mm"] == 60.0
      and by_year[1990]["total_mm"] == 120.0, by_year[1990])
check("1992 complete grace aux mois de 1993", by_year[1992]["complete"] is True)
# Janvier a mars 1993 appartiennent a la saison chaude 1992 : l'annee 1993
# n'a donc aucun mois a elle, et ne doit pas apparaitre comme une annee seche
check("une annee dont les mois sont pris par la saison d'avant disparait",
      1993 not in by_year, sorted(by_year))
check("les annees vides de la fin sont retirees",
      bs.aggregate(months, 1990, 1999)[-1]["year"] == 1992)

# Annee presente mais incomplete : trois mois de saison fraiche en 1993
partial = dict(months)
for m in (4, 5, 6):
    partial[f"1993{m:02d}"] = 10.0
p93 = {r["year"]: r for r in bs.aggregate(partial, 1990, 1999)}[1993]
check("annee incomplete marquee et comptee pour ce qu'elle a",
      p93["complete"] is False and p93["cool_months"] == 3
      and p93["cool_mm"] == 30.0, p93)
check("annee incomplete : pas de total trompeur",
      p93["warm_mm"] is None and p93["total_mm"] is None, p93)
check("une annee incomplete sort des moyennes",
      bs.norms(bs.aggregate(partial, 1990, 1999))["years"] == 3)

n = bs.norms(rows)
check("moyennes sur les seules annees completes",
      n["years"] == 3 and n["total_mm"] == 120.0 and n["from"] == 1990
      and n["to"] == 1992, n)
check("part de la saison chaude", n["warm_share"] == 50, n)

# Une annee humide doit se classer premiere
wet = dict(months)
for m in range(1, 13):
    wet[f"1991{m:02d}"] = 40.0
r91 = bs.rank_of(bs.aggregate(wet, 1990, 1993), 1991)
check("rang de l'annee la plus humide", r91 and r91["rank"] == 1, r91)


# ── Ponderation par le cosinus de la latitude ───────────────────

outline, kind = bo.load_outline({})
digest = bs.outline_digest(outline)
check("empreinte du contour stable", digest == bs.outline_digest(outline))
check("empreinte differente si le contour change",
      bs.outline_digest([(x + 1, y) for x, y in outline]) != digest)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    bs.OUT_FILE = td / "basin_seasons.json"
    bs.CACHE_FILE = td / "season_cache.json"
    bs.TMP_DIR = td / "tmp"

    # Champ croissant vers le sud : la ponderation doit deplacer la moyenne
    field = np.tile((np.arange(NY) * 0.1).reshape(-1, 1), (1, NX)).astype("float32")
    write_geotiff(td / "g.tif", field)
    mean_w, (mask, w) = bs.grid_mean(td / "g.tif", outline)
    plain = float(field[mask].mean())
    check("la moyenne ponderee differe de la moyenne brute",
          abs(mean_w - plain) > 1e-6, f"{mean_w} vs {plain}")
    # Verification a la main sur le meme masque
    wref = np.cos(np.deg2rad(lats))[:, None] * mask
    expect = float((wref * field).sum() / wref.sum())
    check("moyenne ponderee conforme au calcul direct",
          abs(mean_w - expect) < 1e-6, f"{mean_w} vs {expect}")
    # Le champ croit vers le sud et le sud pese moins : la moyenne baisse
    check("le sud pese moins", mean_w < plain, f"{mean_w} vs {plain}")
    check("le masque couvre une part plausible du bassin",
          0.05 < mask.mean() < 0.95, mask.mean())

    # ── Mailles sans donnee ──
    holed = field.copy()
    holed[mask] = np.where(np.arange(int(mask.sum())) % 2 == 0,
                           np.nan, holed[mask])
    write_geotiff(td / "h.tif", np.nan_to_num(holed, nan=-32767.0))
    mean_h, _ = bs.grid_mean(td / "h.tif", outline)
    check("les mailles sans donnee sont ignorees, pas comptees zero",
          np.isfinite(mean_h) and mean_h > 0, mean_h)

    # ── Cache : aller-retour et invalidation ──
    bs.save_cache({"199001": 12.5}, digest, kind, int(mask.sum()))
    got, reset = bs.load_cache(digest)
    check("cache relu", got == {"199001": 12.5} and reset is None, (got, reset))
    got2, reset2 = bs.load_cache("0000000000000000")
    check("cache vide si le contour a change", got2 == {} and reset2, reset2)
    raw = json.loads(bs.CACHE_FILE.read_text(encoding="utf-8"))
    check("le cache porte l'empreinte et le type de contour",
          raw["outline"] == digest and raw["outline_kind"] == kind)
    bs.CACHE_FILE.write_text("{ pas du json", encoding="utf-8")
    got3, reset3 = bs.load_cache(digest)
    check("cache illisible : on repart de zero, sans planter",
          got3 == {} and reset3, reset3)

    # ── Mois manquants : 404 saute, le reste est signale ──
    seen = []

    def fake_download(url, dest, timeout=120):
        seen.append(url)
        if "199003" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        if "199005" in url:
            raise urllib.error.HTTPError(url, 500, "Server Error", None, None)
        write_geotiff(dest, field)

    bs.download = fake_download
    got, cells, errs = bs.fill({}, 1990, 1990, outline, date(1990, 6, 15),
                               from_daily=False, quiet=True,
                               digest=digest, kind=kind)
    check("les mois publies sont tous la",
          sorted(got) == ["199001", "199002", "199004", "199006"], sorted(got))
    check("un 404 ne fait pas d'avertissement", not any("404" in e for e in errs), errs)
    check("une erreur 500 est signalee", any("500" in e for e in errs), errs)
    check("on ne cherche pas au-dela du mois en cours",
          not any("199007" in u for u in seen), seen[-3:])
    check("le nombre de mailles est reporte", cells == int(mask.sum()), cells)

    # ── Grilles mensuelles injoignables : arret net ──
    bs.monthly_available = lambda *a, **k: (False, "403")
    try:
        bs.run(cfg={}, first=1990, last=1990, quiet=True, write=False)
        check("arret si les grilles mensuelles ne repondent pas", False)
    except RuntimeError as e:
        check("arret si les grilles mensuelles ne repondent pas",
              "from-daily" in str(e), str(e)[:80])

    # ── Passage complet, chemin nominal ──
    bs.monthly_available = lambda *a, **k: (True, "ok")
    bs.CACHE_FILE.unlink(missing_ok=True)
    p = bs.run(cfg={}, first=1990, last=1990, quiet=True, write=True)
    check("le JSON est ecrit", bs.OUT_FILE.exists())
    check("le payload porte la source et la licence",
          "SILO" in p["source"] and p["licence"] == "CC BY 4.0")
    check("la definition des saisons voyage avec les donnees",
          p["seasons"]["warm"]["months"] == list(bs.WARM)
          and "October" in p["seasons"]["warm"]["note"])
    check("la ponderation est declaree",
          p["basin"]["weighting"] == "cosine of latitude")
    check("pas de marque demo sur un vrai passage", "demo" not in p)
    check("le cache est conserve pour le prochain passage", bs.CACHE_FILE.exists())

    # Deuxieme passage : rien a retelecharger hors mois recents
    before = len(seen)
    bs.run(cfg={}, first=1990, last=1990, quiet=True, write=False)
    check("le cache evite de retelecharger", len(seen) - before <= 3,
          len(seen) - before)

    # ── Mode demo ──
    quiet_before = len(seen)
    d = bs.run(cfg={}, first=1990, last=1992, demo=True, quiet=True, write=False)
    check("le mode demo est marque", d.get("demo") is True)
    check("le mode demo ne touche pas au reseau", len(seen) == quiet_before,
          len(seen) - quiet_before)
    check("le mode demo produit une serie", len(d["series"]) == 3, len(d["series"]))


# ── Mois recents repris ─────────────────────────────────────────

keys = bs.recent_keys(date(2026, 1, 15), 2)
check("les mois recents remontent par-dessus le changement d'annee",
      keys == ["202601", "202512", "202511"], keys)


bad = [c for c, ok in checks if not ok]
if bad:
    print(f"\n{len(bad)}/{len(checks)} verifications en echec")
    sys.exit(1)
print(f"OK — {len(checks)} verifications : decoupage des saisons, completude, "
      "moyennes, ponderation par la latitude, cache et son invalidation, "
      "mois manquants, arret si les grilles mensuelles manquent, mode demo.")
