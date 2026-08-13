#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de l'export statique (pipeline/export_static.py).

Verifie que le site produit contient tout ce dont le frontend a besoin
et que la reconstruction cote client est fidele :
  - structure du site et du manifeste ;
  - bornes de couleur communes a tous les scenarios ;
  - reconstruction des fleches a partir des indices compactes — c'est
    la que se glisse facilement un decalage d'une demi-maille, `bounds`
    (cadre de l'image) et `extent` (emprise des points) ne coincidant
    pas ;
  - images RGBA valides, transparentes hors du lac ;
  - JSON strictement conforme (le navigateur refuse NaN).

Execution :  python tests/test_export_static.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import yaml
from scipy.io import netcdf_file

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import scenario_field as sf  # noqa: E402

sf.open_dataset = lambda p: netcdf_file(str(p), "r", mmap=False)

import export_static as ex  # noqa: E402

ex.sfield.open_dataset = sf.open_dataset

TMP = Path(tempfile.mkdtemp())
ARCH = TMP / "archive"
(ARCH / "Output" / "Flow").mkdir(parents=True)
(ARCH / "Output" / "wave").mkdir(parents=True)

# ── Archive synthétique : grille tournée, lac ellipsoïdal ────
NN, NM = 50, 40
gi, gj = np.meshgrid(np.linspace(0, 1, NM), np.linspace(0, 1, NN))
ang = np.deg2rad(20.0)
XX = 673229 + (gi * np.cos(ang) - gj * np.sin(ang)) * 120000
YY = 6778805 + (gi * np.sin(ang) + gj * np.cos(ang)) * 130000
LAKE = ((gi - 0.45) / 0.30) ** 2 + ((gj - 0.5) / 0.42) ** 2 <= 1

SPECS = [(5.0, 0.0, -9.0, 250.0), (15.0, 90.0, -11.0, 150.0),
         (25.0, 180.0, -13.0, 50.0)]
entries = []
for sp, di, wl, sal in SPECS:
    key = f"wind-sp{sp}_wind-dir{di}_wlvl{wl}_sal{sal}"
    fp = ARCH / "Output" / "Flow" / f"{key}.nc"
    wp = ARCH / "Output" / "wave" / f"wave_{key}.nc"

    f = netcdf_file(str(fp), "w")
    f.createDimension("time", 3); f.createDimension("KMAXOUT_RESTR", 10)
    f.createDimension("N", NN); f.createDimension("M", NM)
    xv = f.createVariable("XZ", "f8", ("N", "M")); xv[:] = np.where(LAKE, XX, 0)
    yv = f.createVariable("YZ", "f8", ("N", "M")); yv[:] = np.where(LAKE, YY, 0)
    s1 = f.createVariable("S1", "f", ("time", "N", "M"))
    u = f.createVariable("U1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    v = f.createVariable("V1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    for t in range(3):
        s1[t] = np.where(LAKE, wl, 0).astype("f")
        for k in range(10):
            u[t, k] = np.where(LAKE, 0.02 * sp * (1 - 0.05 * k), 0).astype("f")
            v[t, k] = np.where(LAKE, 0.01 * sp, 0).astype("f")
    s1.units = "m"; s1.long_name = "Water-level in zeta point"
    u.units = "m/s"; u.location = "edge1"
    u.long_name = "U-velocity per layer in U-point (Eulerian)"
    v.units = "m/s"; v.location = "edge2"
    f.close()

    f = netcdf_file(str(wp), "w")
    f.createDimension("time", 5)
    f.createDimension("nmax", NN); f.createDimension("mmax", NM)
    xv = f.createVariable("x", "f8", ("nmax", "mmax")); xv[:] = np.where(LAKE, XX, 0)
    yv = f.createVariable("y", "f8", ("nmax", "mmax")); yv[:] = np.where(LAKE, YY, 0)
    dp = f.createVariable("depth", "f", ("time", "nmax", "mmax"))
    for t in range(5):
        dp[t] = np.where(LAKE, 15.2 + wl, 0).astype("f")
    dp.units = "m"; dp.long_name = "Water depth"
    for nm_, un, amp in [("hsign", "m", 0.03 * sp), ("wlength", "m", 1.2 * sp),
                         ("period", "sec", 0.2 * sp), ("dir", "deg", 315.0)]:
        vv = f.createVariable(nm_, "f", ("time", "nmax", "mmax"))
        for t in range(5):
            vv[t] = np.where(LAKE, amp, 0).astype("f")
        vv.units = un
    f.close()

    entries.append({"key": key,
                    "params": {"wind_speed": sp, "wind_dir": di,
                               "wlvl": wl, "salinity": sal},
                    "files": {"flow": str(fp), "wave": str(wp)}})

index_path = TMP / "scenarios.json"
index_path.write_text(json.dumps({
    "demo": False, "directory": str(ARCH), "grid": {},
    "units": {"wind_speed": "m/s"}, "labels": {"wind_speed": "Wind speed"},
    "scenarios": entries}), encoding="utf-8")

# L'exportateur lit l'index à un emplacement fixe : on le pointe ici
_real_root = ex.ROOT
ex.ROOT = TMP
(TMP / "data").mkdir(exist_ok=True)
shutil.copy(index_path, TMP / "data" / "scenarios.json")
shutil.copytree(_real_root / "frontend", TMP / "frontend", dirs_exist_ok=True)

with open(_real_root / "config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
cfg["scenarios"]["directory"] = str(ARCH)

SITE = TMP / "site"
ex.build(cfg, out_dir=SITE, colors=64)

# ── Structure ────────────────────────────────────────────────
for name in ("manifest.json", "index.html", "app.js", "style.css",
             "methods.js", "windrose.js", ".nojekyll",
             "data/scenarios.json"):
    assert (SITE / name).exists(), f"{name} manquant"

man = json.loads((SITE / "manifest.json").read_text(encoding="utf-8"))
assert man["n_scenarios"] == 3
assert set(man["bounds"]) == {"flow", "wave"}
assert set(man["extent"]) == {"flow", "wave"}
assert man["matching"]["wlvl_site"] == cfg["scenarios"]["wlvl_site"]

layer_ids = {l["id"] for l in man["layers"]}
assert layer_ids == {"currents", "hsign", "wlength", "period"}

# Une image et une entrée de flèches par scénario et par couche
n_layers_files = len(list((SITE / "img").glob("*.png")))
assert n_layers_files == 3 * len(man["scales"]), n_layers_files
assert len(list((SITE / "layers").glob("*.json"))) == 3

# ── Bornes de couleur communes ───────────────────────────────
# Elles doivent être identiques pour tous les scénarios, sans quoi les
# couleurs sauteraient en parcourant la frise temporelle.
assert man["scales"]["currents_0"] == [0.0, 0.5], man["scales"]
for lid in ("hsign", "wlength", "period"):
    lo, hi = man["scales"][lid]
    assert lo == 0.0 and hi > 0, (lid, lo, hi)

# La borne haute doit couvrir le scénario le plus énergique
strongest = entries[-1]["key"]
packed_strong = json.loads(
    (SITE / "layers" / f"{strongest}.json").read_text(encoding="utf-8"))
assert packed_strong["hsign"]["zmax"] <= man["scales"]["hsign"][1] * 1.05

# ── Reconstruction des flèches (logique du frontend) ─────────
key = entries[1]["key"]
n = man["n_arrows"]
common = dict(grid_res=cfg["scenarios"].get("map_grid_res", 260),
              n_arrows=n, smooth=cfg["scenarios"].get("current_smooth", 2.0),
              wave_dir_convention="from")
lo, hi = man["scales"]["currents_0"]
orig = ex.render(None, cfg, key, entries[1], "currents", 0,
                 dict(common, vmin=lo, vmax=hi))
packed = json.loads(
    (SITE / "layers" / f"{key}.json").read_text(encoding="utf-8"))["currents_0"]

assert len(packed["i"]) == orig["n_arrows"], (len(packed["i"]),
                                              orig["n_arrows"])
(lat0, lon0), (lat1, lon1) = man["extent"]["flow"]
rlat = [lat0 + (lat1 - lat0) * ((f // n) / (n - 1)) for f in packed["i"]]
rlon = [lon0 + (lon1 - lon0) * ((f % n) / (n - 1)) for f in packed["i"]]
dlat = np.abs(np.array(rlat) - np.array(orig["arrows"]["lat"])).max()
dlon = np.abs(np.array(rlon) - np.array(orig["arrows"]["lon"])).max()
assert dlat * 111320 < 1.0, f"flèches décalées de {dlat * 111320:.0f} m en lat"
assert dlon * 97000 < 1.0, f"flèches décalées de {dlon * 97000:.0f} m en lon"

# `bounds` et `extent` diffèrent bien d'une demi-maille : les confondre
# décalerait les flèches d'environ 200 m.
blat0 = man["bounds"]["flow"][0][0]
assert blat0 < lat0 - 1e-9, "bounds doit être plus large que extent"

assert np.abs(np.array(packed["b"])
              - np.array(orig["arrows"]["bearing"])).max() <= 0.05
assert np.abs(np.array(packed["v"])
              - np.array(orig["arrows"]["value"])).max() <= 5e-5

# ── Images ───────────────────────────────────────────────────
from PIL import Image  # noqa: E402

img = Image.open(SITE / "img" / f"{key}__currents_0.png")
assert img.mode == "RGBA" and img.size == (common["grid_res"],) * 2
arr = np.array(img)
opaque = (arr[..., 3] > 0).mean()
# Le lac occupe environ pi/4 de son cadre englobant
assert 0.5 < opaque < 0.95, opaque
assert (arr[..., 3] == 0).any(), "le hors-lac doit être transparent"

# ── JSON strictement conforme ────────────────────────────────
def _strict(c):
    raise ValueError("constante JSON interdite : " + c)


n_json = 0
for f in SITE.rglob("*.json"):
    json.loads(f.read_text(encoding="utf-8"), parse_constant=_strict)
    n_json += 1
assert n_json >= 5

# ── Index allégé : pas de chemins absolus ────────────────────
slim = json.loads((SITE / "data" / "scenarios.json").read_text(encoding="utf-8"))
assert slim["n_scenarios"] == 3
assert all("files" not in s for s in slim["scenarios"]), \
    "les chemins du disque ne doivent pas être publiés"
assert all("params" in s and "key" in s for s in slim["scenarios"])

ex.ROOT = _real_root
print("OK — export statique : structure, bornes communes, reconstruction "
      "des flèches au mètre près, images transparentes et JSON conforme.")
