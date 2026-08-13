#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la base de scenarios Delft3D (sans NetCDF).

Verifie :
  - le parsing du nom de fichier reel
    (wave_wind-sp29.0_wind-dir90.0_wlvl-9.0_sal100.0.nc) ;
  - les deux conventions de signe pour wlvl ;
  - le rejet des noms non conformes ;
  - la construction de la grille ;
  - l'appariement : normalisation par le pas de grille, direction
    circulaire (350 deg plus proche de 0 que de 315) ;
  - la detection hors enveloppe (niveau plus bas que tout scenario) ;
  - la conversion km/h -> m/s et la convention de direction.

Execution :  python tests/test_scenarios.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import scenarios as sc  # noqa: E402

# Noms reels fournis par l'utilisatrice (separateur decimal = underscore)
WAVE_NAME = "wave_wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc"
FLOW_NAME = "wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc"

rx = sc.build_regex()

# ── Parsing des noms reels ───────────────────────────────────
expected = {"wind_speed": 1.0, "wind_dir": 0.0, "wlvl": -7.0,
            "salinity": 250.0}
assert sc.parse_scenario_filename(WAVE_NAME, rx) == expected
assert sc.parse_scenario_filename(FLOW_NAME, rx) == expected

# Underscore decimal : une valeur non entiere doit etre lue en entier
frac = "wave_wind-sp12_5_wind-dir315_0_wlvl-13_5_sal50_0.nc"
pf = sc.parse_scenario_filename(frac, rx)
assert pf["wind_speed"] == 12.5, pf          # et non 12
assert pf["wlvl"] == -13.5 and pf["salinity"] == 50.0
assert pf["wind_dir"] == 315.0

# Le motif "wind-sp" ne doit pas etre confondu avec "wind-dir"
assert sc.parse_scenario_filename(
    "wave_wind-sp3_0_wind-dir270_0_wlvl-9_0_sal0_0.nc", rx) == {
    "wind_speed": 3.0, "wind_dir": 270.0, "wlvl": -9.0, "salinity": 0.0}

# Notation pointee (ancienne convention) toujours acceptee
dotted = "wave_wind-sp29.0_wind-dir90.0_wlvl-9.0_sal100.0.nc"
assert sc.parse_scenario_filename(dotted, rx) == {
    "wind_speed": 29.0, "wind_dir": 90.0, "wlvl": -9.0, "salinity": 100.0}

# ── Cle commune WAVE / FLOW ──────────────────────────────────
assert sc.scenario_key(WAVE_NAME) == sc.scenario_key(FLOW_NAME)
assert sc.scenario_key(WAVE_NAME) == "wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0"

# ── Convention de signe alternative ──────────────────────────
rx_pos = sc.build_regex(wlvl_sign="positive")
assert sc.parse_scenario_filename(WAVE_NAME, rx_pos)["wlvl"] == 7.0

# Niveau positif ecrit sans tiret : lu pareil dans les deux conventions
name_pos = "wave_wind-sp5_0_wind-dir0_0_wlvl2_5_sal100_0.nc"
assert sc.parse_scenario_filename(name_pos, rx)["wlvl"] == 2.5
assert sc.parse_scenario_filename(name_pos, rx_pos)["wlvl"] == 2.5

# ── Noms non conformes ───────────────────────────────────────
assert sc.parse_scenario_filename("wave_wind-sp5_0_wlvl-9_0.nc", rx) is None
assert sc.parse_scenario_filename("readme.txt", rx) is None

# ── Grille ───────────────────────────────────────────────────
def make(sp, di, wl, sal=100.0):
    def f(v):
        return f"{v:.1f}".replace(".", "_")
    key = f"wind-sp{f(sp)}_wind-dir{f(di)}_wlvl{f(wl)}_sal{f(sal)}"
    return {"key": key,
            "files": {"wave": f"Output/Wave/wave_{key}.nc",
                      "flow": f"Output/Flow/{key}.nc"},
            "params": {"wind_speed": sp, "wind_dir": di,
                       "wlvl": wl, "salinity": sal}}

scen = [make(sp, di, wl)
        for sp in (5.0, 10.0, 15.0, 20.0)
        for di in (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)
        for wl in (-14.0, -13.0, -12.0, -11.0)]
grid = sc.build_grid(scen)
assert grid["wind_speed"] == [5.0, 10.0, 15.0, 20.0]
assert grid["wlvl"] == [-14.0, -13.0, -12.0, -11.0]
assert len(grid["wind_dir"]) == 8
assert sc.median_step(grid["wind_speed"]) == 5.0
assert sc.median_step([3.0]) == 1.0, "une seule valeur -> pas neutre"

# ── Ecart circulaire ─────────────────────────────────────────
assert sc.circular_delta(10.0, 350.0) == 20.0
assert sc.circular_delta(350.0, 10.0) == -20.0
assert abs(sc.circular_delta(180.0, 0.0)) == 180.0

# ── Appariement simple ───────────────────────────────────────
r = sc.match_scenario(scen, grid,
                      {"wind_speed": 14.2, "wind_dir": 88.0, "wlvl": -12.9},
                      mode="step")
q = r["scenario"]["params"]
assert q["wind_speed"] == 15.0 and q["wind_dir"] == 90.0 and q["wlvl"] == -13.0
assert abs(r["deltas"]["wind_speed"] - (-0.8)) < 1e-9
assert all(v == "in" for v in r["envelope"].values())

# ── Direction circulaire : 350 deg doit tomber sur 0, pas 315 ──
r = sc.match_scenario(scen, grid,
                      {"wind_speed": 10.0, "wind_dir": 350.0, "wlvl": -13.0},
                      mode="step")
assert r["scenario"]["params"]["wind_dir"] == 0.0, \
    "la direction doit etre traitee circulairement"
assert abs(r["deltas"]["wind_dir"] - (-10.0)) < 1e-9

# ── Hors enveloppe : niveau plus bas que toute simulation ────
r = sc.match_scenario(scen, grid,
                      {"wind_speed": 10.0, "wind_dir": 90.0, "wlvl": -16.5},
                      mode="step")
assert r["envelope"]["wlvl"] == "below"
assert r["scenario"]["params"]["wlvl"] == -14.0, "borne la plus proche"
assert any("below the simulated" in w for w in r["warnings"]), r["warnings"]

r = sc.match_scenario(scen, grid,
                      {"wind_speed": 35.0, "wind_dir": 90.0, "wlvl": -12.0},
                      mode="step")
assert r["envelope"]["wind_speed"] == "above"
assert any("above the simulated" in w for w in r["warnings"])

# ── Grille creuse : le plus proche disponible ────────────────
sparse = [make(5.0, 0.0, -13.0), make(20.0, 180.0, -11.0)]
rs = sc.match_scenario(sparse, sc.build_grid(sparse),
                       {"wind_speed": 18.0, "wind_dir": 170.0, "wlvl": -11.2},
                       mode="step")
assert rs["scenario"]["params"]["wind_speed"] == 20.0

# ── Ponderation : ignorer un parametre ───────────────────────
r0 = sc.match_scenario(scen, grid,
                       {"wind_speed": 5.0, "wind_dir": 90.0, "wlvl": -11.4},
                       weights={"wlvl": 0.0}, mode="step")
assert r0["scenario"]["params"]["wind_speed"] == 5.0

# ── Conversion des conditions observees ──────────────────────
kmh, ms = 31.0, 31.0 / 3.6
assert abs(ms - 8.611) < 1e-3, "km/h -> m/s"
# Convention "to" : la direction BOM (provenance) est retournee de 180
assert (157.5 + 180.0) % 360.0 == 337.5

# ── Echelles de normalisation ────────────────────────────────
sc_range = sc.build_scales(grid, "range")
sc_step = sc.build_scales(grid, "step")
assert sc_range["wind_dir"] == 180.0 and sc_step["wind_dir"] == 180.0, \
    "la direction est circulaire : echelle 180 deg dans les deux modes"
assert sc_range["wind_speed"] == 15.0   # 20 - 5
assert sc_step["wind_speed"] == 5.0
assert sc.build_scales({"sal": [100.0]}, "range")["sal"] == 1.0, \
    "une seule valeur -> echelle neutre"

# ── Alternatives classees ────────────────────────────────────
r = sc.match_scenario(scen, grid,
                      {"wind_speed": 14.2, "wind_dir": 88.0, "wlvl": -12.9},
                      n_alternatives=3)
assert len(r["alternatives"]) == 3
dists = [a["distance"] for a in r["alternatives"]]
assert dists == sorted(dists), "alternatives triees par distance"
assert all(d >= r["distance"] for d in dists)

# ── Regroupement WAVE / FLOW sur disque ──────────────────────
import tempfile
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "Output" / "Wave").mkdir(parents=True)
    (root / "Output" / "Flow").mkdir(parents=True)
    (root / "Output" / "Wave" / WAVE_NAME).write_bytes(b"x")
    (root / "Output" / "Flow" / FLOW_NAME).write_bytes(b"x")
    (root / "Output" / "Wave" / "notes.txt").write_bytes(b"x")

    found, rep = sc.scan_directory(str(root), rx, verify_format=False)
    assert len(found) == 1, "les deux sorties = un seul scenario"
    entry = found[0]
    assert set(entry["files"]) == {"wave", "flow"}
    assert entry["files"]["wave"].endswith(WAVE_NAME)
    assert entry["files"]["flow"].endswith(FLOW_NAME)
    assert entry["params"] == expected
    assert rep["unnamed"] == [] and rep["junk"] == []

    # Sortie FLOW seule (run WAVE absent)
    solo = "wind-sp9_0_wind-dir45_0_wlvl-11_0_sal0_0.nc"
    (root / "Output" / "Flow" / solo).write_bytes(b"x")
    found2, _ = sc.scan_directory(str(root), rx, verify_format=False)
    assert len(found2) == 2
    lone = [s for s in found2 if s["key"].startswith("wind-sp9_0")][0]
    assert set(lone["files"]) == {"flow"}

# ── Classement de la source ──────────────────────────────────
assert sc.classify_source("/x/Output/Wave/" + WAVE_NAME) == "wave"
assert sc.classify_source("/x/Output/Flow/" + FLOW_NAME) == "flow"
assert sc.classify_source("/x/ailleurs/" + WAVE_NAME) == "wave", \
    "le prefixe prime sur le dossier"

print("OK — parsing (underscore décimal), appariement WAVE/FLOW, "
      "échelles, alternatives, grille, direction circulaire et "
      "hors-enveloppe validés.")

# ══════════════════════════════════════════════════════════════
# Plan d'experience (lhs_all.csv)
# ══════════════════════════════════════════════════════════════

import csv as _csv

with tempfile.TemporaryDirectory() as td:
    design_path = Path(td) / "lhs_all.csv"
    rows = [
        {"wind_sp": 25.0, "wind_dir": 0.0, "wlvl": -7.0, "sal": 150.0},
        {"wind_sp": 25.0, "wind_dir": 180.0, "wlvl": -8.5, "sal": 200.0},
        {"wind_sp": 20.0, "wind_dir": 45.0, "wlvl": -13.5, "sal": 250.0},
        {"wind_sp": 1.0, "wind_dir": 0.0, "wlvl": -7.0, "sal": 250.0},
    ]
    with open(design_path, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["wind_sp", "wind_dir", "wlvl", "sal"])
        w.writeheader()
        w.writerows(rows)

    design = sc.read_design(design_path)
    assert len(design) == 4
    assert design[0] == {"wind_speed": 25.0, "wind_dir": 0.0,
                         "wlvl": -7.0, "salinity": 150.0}

    # Deux runs presents sur quatre prevus, plus un run hors plan
    present = [make(25.0, 0.0, -7.0, 150.0),
               make(1.0, 0.0, -7.0, 250.0),
               make(33.0, 90.0, -10.0, 50.0)]
    cov = sc.design_coverage(design, present)
    assert cov["n_design"] == 4 and cov["n_design_unique"] == 4
    assert cov["n_done"] == 2, cov
    assert cov["n_missing"] == 2
    assert cov["n_extra"] == 1
    missing_sp = {round(r["wind_speed"], 1) for r in cov["missing_sample"]}
    assert missing_sp == {25.0, 20.0}, missing_sp

    # Les doublons du plan ne comptent qu'une fois
    design_dup = design + [design[0]]
    cov2 = sc.design_coverage(design_dup, present)
    assert cov2["n_design"] == 5 and cov2["n_design_unique"] == 4

print("OK — lecture du plan d'expérience et couverture des runs validées.")

# ══════════════════════════════════════════════════════════════
# Fichiers parasites macOS et validation de l'entete NetCDF
# ══════════════════════════════════════════════════════════════

HDF5_MAGIC = b"\x89HDF\r\n\x1a\n" + b"\x00" * 24
CDF_MAGIC = b"CDF\x01" + b"\x00" * 28

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    wave = root / "Output" / "wave"      # dossier en minuscules, comme en vrai
    flow = root / "Output" / "Flow"
    wave.mkdir(parents=True); flow.mkdir(parents=True)

    # Nom reel avec separateur decimal pointe
    base = "wind-sp2.0_wind-dir0.0_wlvl-13.0_sal250.0"
    (wave / f"wave_{base}.nc").write_bytes(HDF5_MAGIC)
    (flow / f"{base}.nc").write_bytes(CDF_MAGIC)

    # AppleDouble : meme nom precede de "._", contenu non NetCDF
    (wave / f"._wave_{base}.nc").write_bytes(b"\x00\x05\x16\x07junk")
    (flow / f"._{base}.nc").write_bytes(b"\x00\x05\x16\x07junk")

    # Autres parasites
    (root / "Output" / "__MACOSX").mkdir()
    (root / "Output" / "__MACOSX" / f"wave_{base}.nc").write_bytes(b"junk")
    (wave / ".DS_Store").write_bytes(b"junk")
    # Fichier tronque portant un nom valide
    trunc = "wind-sp9.0_wind-dir45.0_wlvl-11.0_sal0.0"
    (flow / f"{trunc}.nc").write_bytes(b"not a netcdf at all")

    found, rep = sc.scan_directory(str(root), rx)

    assert len(found) == 1, f"un seul scenario attendu, {len(found)} trouves"
    entry = found[0]
    assert entry["key"] == base, entry["key"]
    assert set(entry["files"]) == {"wave", "flow"}
    assert not Path(entry["files"]["wave"]).name.startswith("._"), \
        "le fichier retenu ne doit jamais etre un AppleDouble"
    assert entry["params"] == {"wind_speed": 2.0, "wind_dir": 0.0,
                               "wlvl": -13.0, "salinity": 250.0}

    # .DS_Store ne finit pas par .nc : hors du parcours\n    assert len(rep["junk"]) == 3, rep["junk"]   # 2 AppleDouble + __MACOSX
    assert any("._wave_" in n for n in rep["junk"])
    assert any("__MACOSX" in n for n in rep["junk"])
    assert any(n.endswith(f"{trunc}.nc") for n in rep["bad_format"]), \
        rep["bad_format"]

    # Sans verification d'entete, le fichier tronque passe mais pas les ._*
    found2, rep2 = sc.scan_directory(str(root), rx, verify_format=False)
    assert len(found2) == 2
    assert not any(k.startswith("._") for k in (s["key"] for s in found2))

# ── Detection unitaire ───────────────────────────────────────
assert sc.is_junk_path("/x/Output/wave/._wave_a.nc")
assert sc.is_junk_path("/x/Output/wave/.DS_Store")
assert sc.is_junk_path("/x/__MACOSX/wave_a.nc")
assert not sc.is_junk_path("/x/Output/wave/wave_a.nc")

print("OK — fichiers macOS ._*, dossiers cachés et en-têtes NetCDF "
      "invalides correctement écartés.")

# ══════════════════════════════════════════════════════════════
# Arrondi du niveau d'eau vers le bas.
#
# Retenir un scenario dont le niveau depasse l'observe simulerait plus
# d'eau qu'il n'y en a : a -12.4 m sur un fond vers -15.2 m, passer a
# -12.0 m ajoute 14 % de tirant d'eau, et bien davantage a mesure que
# le lac s'assèche.
# ══════════════════════════════════════════════════════════════


def scen_at(sp, di, wl, sal=250.0):
    return {"key": f"sp{sp}_dir{di}_wl{wl}", "files": {},
            "params": {"wind_speed": sp, "wind_dir": di,
                       "wlvl": wl, "salinity": sal}}


# Vent identique : seul le niveau départage
pair = [scen_at(10.0, 90.0, -12.0), scen_at(10.0, 90.0, -14.0)]
grid_pair = sc.build_grid(pair)
target_mid = {"wind_speed": 10.0, "wind_dir": 90.0, "wlvl": -12.4,
              "salinity": 250.0}

r_near = sc.match_scenario(pair, grid_pair, target_mid, wlvl_mode="nearest")
assert r_near["scenario"]["params"]["wlvl"] == -12.0, "plus proche : -12.0"
assert r_near["wlvl_capped"] is False

r_down = sc.match_scenario(pair, grid_pair, target_mid, wlvl_mode="down")
assert r_down["scenario"]["params"]["wlvl"] == -14.0, (
    "vers le bas : aucun niveau au-dessus de l'observé n'est admissible")
assert r_down["wlvl_capped"] is True
assert r_down["deltas"]["wlvl"] > 0, "l'écart devient positif : moins d'eau"

# Un niveau exactement egal est admissible
exact = [scen_at(10.0, 90.0, -12.4), scen_at(10.0, 90.0, -12.0)]
r_eq = sc.match_scenario(exact, sc.build_grid(exact), target_mid,
                         wlvl_mode="down")
assert r_eq["scenario"]["params"]["wlvl"] == -12.4

# Le mode par defaut reste "nearest" : le comportement ne change pas
# sans configuration explicite.
r_def = sc.match_scenario(pair, grid_pair, target_mid)
assert r_def["scenario"]["params"]["wlvl"] == -12.0

# Repli : si TOUS les scenarios sont au-dessus, on garde le plus proche
# plutot que de ne rien afficher, et l'enveloppe le signale.
high = [scen_at(10.0, 90.0, -9.0), scen_at(12.0, 90.0, -8.0)]
r_high = sc.match_scenario(high, sc.build_grid(high), target_mid,
                           wlvl_mode="down")
assert r_high["wlvl_capped"] is False
assert r_high["envelope"]["wlvl"] == "below"
assert any("below the simulated" in w for w in r_high["warnings"])

# candidate_pool : filtrage direct
pool, capped = sc.candidate_pool(pair, target_mid, "down")
assert len(pool) == 1 and capped is True
pool2, capped2 = sc.candidate_pool(pair, target_mid, "nearest")
assert len(pool2) == 2 and capped2 is False
# Cible sans niveau : aucun filtrage possible
pool3, capped3 = sc.candidate_pool(pair, {"wind_speed": 10.0}, "down")
assert len(pool3) == 2 and capped3 is False

# L'écart de niveau volontaire ne doit pas être signalé comme un défaut
sparse = [scen_at(10.0, 90.0, -14.0), scen_at(10.0, 90.0, -12.0)]
r_sp = sc.match_scenario(sparse, sc.build_grid(sparse), target_mid,
                         wlvl_mode="down")
assert not any("Water level" in w and "away from" in w
               for w in r_sp["warnings"]), r_sp["warnings"]

print("OK — arrondi du niveau vers le bas : filtrage, égalité, repli et "
      "absence d'avertissement superflu validés.")
