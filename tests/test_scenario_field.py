#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du lecteur de champs Delft3D (pipeline/scenario_field.py).

netCDF4 n'etant pas requis pour ce test, les fichiers sont ecrits et
relus avec scipy.io.netcdf_file (API compatible pour ce qui est
utilise ici : .variables, .dimensions, attributs, .close()).

Verifie :
  - detection des coordonnees et des champs 2D ;
  - choix automatique de la variable (Hs prioritaire sur une variable
    inconnue) ;
  - reduction de la dimension temporelle (dernier pas) ;
  - sous-echantillonnage d'une grille reguliere trop dense ;
  - re-echantillonnage d'une grille curviligne (coordonnees 2D) ;
  - transposition quand le champ est (lon, lat) ;
  - NaN -> null dans le JSON, min/max ignorant les NaN ;
  - erreurs explicites (variable absente, champ non 2D).

Execution :  python tests/test_scenario_field.py
"""

import sys
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import scenario_field as sf  # noqa: E402

# scipy remplace netCDF4 pour ce test
sf.open_dataset = lambda path: netcdf_file(str(path), "r", mmap=False)

TMP = Path("/tmp/lke_field_tests")
TMP.mkdir(exist_ok=True)


def write_rectilinear(path, nx=400, ny=300, with_time=True):
    """Grille reguliere lon/lat, champ hsig (+ dimension temps)."""
    f = netcdf_file(str(path), "w")
    f.createDimension("lon", nx)
    f.createDimension("lat", ny)
    lon = f.createVariable("longitude", "f", ("lon",))
    lat = f.createVariable("latitude", "f", ("lat",))
    lon[:] = np.linspace(136.8, 138.2, nx)
    lat[:] = np.linspace(-29.4, -28.2, ny)

    field = np.tile(np.linspace(0, 1.2, nx), (ny, 1)).astype("f")
    if with_time:
        f.createDimension("time", 3)
        v = f.createVariable("hsig", "f", ("time", "lat", "lon"))
        for t in range(3):
            v[t] = field * (t + 1)      # dernier pas = field * 3
    else:
        v = f.createVariable("hsig", "f", ("lat", "lon"))
        v[:] = field
    v.units = "m"
    v.long_name = "significant wave height"

    # Variable inconnue, ne doit pas etre choisie par defaut
    o = f.createVariable("zzz_other", "f", ("lat", "lon"))
    o[:] = field
    f.close()


def write_curvilinear(path, n=60):
    """Coordonnees 2D (grille tournee) + champ avec des NaN."""
    f = netcdf_file(str(path), "w")
    f.createDimension("m", n)
    f.createDimension("n", n)
    i, j = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
    ang = np.deg2rad(20.0)
    x = 136.9 + (i * np.cos(ang) - j * np.sin(ang)) * 1.2
    y = -29.3 + (i * np.sin(ang) + j * np.cos(ang)) * 1.0

    xv = f.createVariable("XZ", "f", ("n", "m")); xv[:] = x.astype("f")
    yv = f.createVariable("YZ", "f", ("n", "m")); yv[:] = y.astype("f")
    z = (i + j).astype("f")
    z[:5, :5] = np.nan                    # zone sechee
    v = f.createVariable("hsig", "f", ("n", "m")); v[:] = z
    v.units = "m"
    f.close()


# ── Grille reguliere ─────────────────────────────────────────
p = TMP / "rect.nc"
write_rectilinear(p)

ds = sf.open_dataset(p)
info = sf.describe_dataset(ds)
ds.close()
assert info["x"] == "longitude" and info["y"] == "latitude"
names = {f["name"] for f in info["fields"]}
assert names == {"hsig", "zzz_other"}, names

out = sf.read_field(p, max_points=100)
assert out["var"] == "hsig", "Hs doit primer sur une variable inconnue"
assert out["label"] == "significant wave height"
assert out["units"] == "m"
assert out["regridded"] is False
assert out["n_x"] <= 100 and out["n_y"] <= 100, "sous-echantillonnage"
assert len(out["z"]) == out["n_y"] and len(out["z"][0]) == out["n_x"]
# Dernier pas de temps : champ x3, max theorique 3.6
assert abs(out["zmax"] - 3.6) < 0.05, out["zmax"]
assert out["x"][0] < out["x"][-1]

# Choix explicite de la variable
out2 = sf.read_field(p, varname="zzz_other", max_points=100)
assert out2["var"] == "zzz_other" and abs(out2["zmax"] - 1.2) < 0.02

# Sans dimension temporelle
p2 = TMP / "rect_notime.nc"
write_rectilinear(p2, nx=50, ny=40, with_time=False)
out3 = sf.read_field(p2, max_points=200)
assert out3["n_x"] == 50 and out3["n_y"] == 40, "pas de sous-echantillonnage"
assert abs(out3["zmax"] - 1.2) < 0.02

# ── Champ transpose (lon, lat) ───────────────────────────────
p3 = TMP / "rect_T.nc"
f = netcdf_file(str(p3), "w")
f.createDimension("lon", 30); f.createDimension("lat", 20)
lo = f.createVariable("lon", "f", ("lon",)); lo[:] = np.linspace(137, 138, 30)
la = f.createVariable("lat", "f", ("lat",)); la[:] = np.linspace(-29, -28, 20)
v = f.createVariable("hsig", "f", ("lon", "lat"))
v[:] = np.tile(np.linspace(0, 1, 20), (30, 1)).astype("f")
f.close()
outT = sf.read_field(p3, max_points=200)
assert len(outT["z"]) == 20 and len(outT["z"][0]) == 30, \
    "le champ (lon, lat) doit etre transpose"

# ── Grille curviligne ────────────────────────────────────────
pc = TMP / "curv.nc"
write_curvilinear(pc)
outc = sf.read_field(pc, max_points=48)
assert outc["regridded"] is True
assert outc["n_x"] == 48 and outc["n_y"] == 48
assert outc["x"][0] < outc["x"][-1] and outc["y"][0] < outc["y"][-1]
flat = [v for row in outc["z"] for v in row]
assert any(v is None for v in flat), "les zones sans donnee -> null"
assert any(v is not None for v in flat)
assert outc["zmin"] is not None and outc["zmax"] is not None
assert np.isfinite(outc["zmin"]) and np.isfinite(outc["zmax"])

# ── Erreurs explicites ───────────────────────────────────────
try:
    sf.read_field(p, varname="absente")
    raise AssertionError("une variable absente doit lever une erreur")
except ValueError as e:
    assert "absente" in str(e)

p4 = TMP / "vec.nc"
f = netcdf_file(str(p4), "w")
f.createDimension("lon", 10)
lo = f.createVariable("longitude", "f", ("lon",)); lo[:] = np.arange(10)
la = f.createVariable("latitude", "f", ("lon",)); la[:] = np.arange(10)
f.close()
try:
    sf.read_field(p4)
    raise AssertionError("un fichier sans champ 2D doit lever une erreur")
except ValueError as e:
    assert "2D" in str(e)

# ══════════════════════════════════════════════════════════════
# Structure reelle d'une sortie Delft3D-FLOW
#   XZ/YZ  centres de mailles (2D, coordonnees projetees)
#   S1     (time, N, M)                      zeta point
#   U1     (time, KMAXOUT_RESTR, N, M)       edge1, par couche
#   R1     (time, KMAXOUT_RESTR, LSTSCI, N, M)  constituants
#   TAUMAX (time, N, M)
# ══════════════════════════════════════════════════════════════

def write_flow(path, nm=40, nn=30, nlay=5, ncon=2, ntime=3):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", ntime)
    f.createDimension("KMAXOUT_RESTR", nlay)
    f.createDimension("LSTSCI", ncon)
    f.createDimension("N", nn)
    f.createDimension("M", nm)

    i, j = np.meshgrid(np.linspace(0, 1, nm), np.linspace(0, 1, nn))
    ang = np.deg2rad(15.0)
    # coordonnees projetees (metres, type MGA)
    xz = f.createVariable("XZ", "f", ("N", "M"))
    yz = f.createVariable("YZ", "f", ("N", "M"))
    xz[:] = (250000 + (i * np.cos(ang) - j * np.sin(ang)) * 60000).astype("f")
    yz[:] = (6800000 + (i * np.sin(ang) + j * np.cos(ang)) * 50000).astype("f")

    s1 = f.createVariable("S1", "f", ("time", "N", "M"))
    for t in range(ntime):
        s1[t] = (0.1 * (t + 1) * i).astype("f")
    s1.units = "m"
    s1.long_name = "Water-level in zeta point"
    s1.location = "face"

    u1 = f.createVariable("U1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    for t in range(ntime):
        for k in range(nlay):
            u1[t, k] = (0.5 * (k + 1) * j).astype("f")   # couche 0 = 0.5*j
    u1.units = "m/s"
    u1.long_name = "U-velocity per layer in U-point (Eulerian)"
    u1.location = "edge1"

    # Ordre reel : (time, LSTSCI, KMAXOUT_RESTR, N, M)
    r1 = f.createVariable("R1", "f",
                          ("time", "LSTSCI", "KMAXOUT_RESTR", "N", "M"))
    for t in range(ntime):
        for c in range(ncon):
            for k in range(nlay):
                r1[t, c, k] = np.full((nn, nm), 250.0 - 10 * c - k, "f")
    r1.units = "g/L"
    r1.long_name = "Concentrations per layer in zeta point"

    tm = f.createVariable("TAUMAX", "f", ("time", "N", "M"))
    for t in range(ntime):
        tm[t] = (0.02 * i).astype("f")
    tm.units = "N/m2"
    tm.long_name = "Tau_max in zeta points (scalar)"

    # Coordonnees des coins : presentes dans les vraies sorties, elles ne
    # doivent pas apparaitre comme des champs physiques
    xc = f.createVariable("XCOR", "f", ("N", "M"))
    yc = f.createVariable("YCOR", "f", ("N", "M"))
    xc[:] = np.zeros((nn, nm), "f"); yc[:] = np.zeros((nn, nm), "f")
    xc.units = "m"; xc.long_name = "X-coordinate of grid points"
    yc.units = "m"; yc.long_name = "Y-coordinate of grid points"
    f.close()


pf = TMP / "flow.nc"
write_flow(pf)

ds = sf.open_dataset(pf)
info = sf.describe_dataset(ds)
ds.close()
assert info["x"] == "XZ" and info["y"] == "YZ", info
assert info["coord_shape"] == (30, 40)
byname = {f["name"]: f for f in info["fields"]}
assert set(byname) == {"S1", "U1", "R1", "TAUMAX"}, set(byname)
assert byname["U1"]["extra_dims"] == ["KMAXOUT_RESTR"]
assert byname["R1"]["extra_dims"] == ["LSTSCI", "KMAXOUT_RESTR"]
assert "XCOR" not in byname and "YCOR" not in byname, \
    "les coordonnées des coins ne sont pas des champs affichables"
assert sf.dim_kind("KMAXOUT_RESTR") == "layer"
assert sf.dim_kind("LSTSCI") == "constituent"
assert sf.dim_kind("time") == "time" and sf.dim_kind("M") == "other"
assert byname["S1"]["location"] == "face"
assert byname["U1"]["location"] == "edge1"
assert all(f["on_coords"] for f in info["fields"]), "memes dimensions N, M"

# S1 : 3D -> dernier pas de temps
o = sf.read_field(pf, varname="S1", max_points=200)
assert o["regridded"] is True, "coordonnees 2D -> re-echantillonnage"
assert abs(o["zmax"] - 0.3) < 0.02, o["zmax"]      # 0.1 * 3
assert any("time" in n for n in o["reduction"]), o["reduction"]
assert o["units"] == "m" and o["location"] == "face"
# coordonnees projetees conservees (metres, pas des degres)
assert o["x"][0] > 100000 and o["y"][0] > 1000000

# U1 : 4D -> temps + couche
o = sf.read_field(pf, varname="U1", max_points=60, layer_index=0)
assert abs(o["zmax"] - 0.5) < 0.02, o["zmax"]      # couche 0
red = " ".join(o["reduction"])
assert "KMAXOUT_RESTR=0 sur 5" in red, o["reduction"]

o2 = sf.read_field(pf, varname="U1", max_points=60, layer_index=4)
assert abs(o2["zmax"] - 2.5) < 0.05, o2["zmax"]    # couche 4 = 0.5*5
o3 = sf.read_field(pf, varname="U1", max_points=60, layer_index=99)
assert abs(o3["zmax"] - 2.5) < 0.05, "indice de couche borne au maximum"

# R1 : 5D -> temps + constituant + couche, pilotes separement
o = sf.read_field(pf, varname="R1", max_points=60)
assert abs(o["zmax"] - 250.0) < 0.5, o["zmax"]        # constituant 0, couche 0
red = " ".join(o["reduction"])
assert "LSTSCI=0 sur 2" in red and "KMAXOUT_RESTR=0 sur 5" in red, o["reduction"]

o = sf.read_field(pf, varname="R1", max_points=60, constituent_index=1)
assert abs(o["zmax"] - 240.0) < 0.5, o["zmax"]        # constituant 1
o = sf.read_field(pf, varname="R1", max_points=60, layer_index=3)
assert abs(o["zmax"] - 247.0) < 0.5, o["zmax"]        # couche 3 : 250 - 3
o = sf.read_field(pf, varname="R1", max_points=60,
                  constituent_index=1, layer_index=2)
assert abs(o["zmax"] - 238.0) < 0.5, \
    f"couche et constituant doivent être indépendants (obtenu {o['zmax']})"

# Axes reduits decrits pour l'interface
o = sf.read_field(pf, varname="U1", max_points=60, layer_index=2)
kinds = {a["kind"]: a for a in o["axes"]}
assert kinds["time"]["size"] == 3 and kinds["time"]["index"] == 2
assert kinds["layer"]["size"] == 5 and kinds["layer"]["index"] == 2
assert kinds["layer"]["dim"] == "KMAXOUT_RESTR"
assert "constituent" not in kinds, "U1 n'a pas de constituant"

o = sf.read_field(pf, varname="S1", max_points=60)
assert [a["kind"] for a in o["axes"]] == ["time"]
assert o["location"] == "face"

# Choix du pas de temps
o = sf.read_field(pf, varname="TAUMAX", max_points=60, time_index=0)
assert abs(o["zmax"] - 0.02) < 0.002, o["zmax"]

# ── Grille decalee : formes incompatibles -> indices de maille ──
pstag = TMP / "stag.nc"
f = netcdf_file(str(pstag), "w")
f.createDimension("N", 20); f.createDimension("M", 30)
f.createDimension("MC", 31); f.createDimension("time", 1)
# Coordonnees realistes aux centres : c'est bien l'ecart de forme
# (31 colonnes contre 30) qui doit declencher le trace sur indices.
gi, gj = np.meshgrid(np.linspace(0, 1, 30), np.linspace(0, 1, 20))
xz = f.createVariable("XZ", "f", ("N", "M"))
yz = f.createVariable("YZ", "f", ("N", "M"))
xz[:] = (500000 + gi * 1000).astype("f")
yz[:] = (6800000 + gj * 1000).astype("f")
uu = f.createVariable("UU", "f", ("time", "N", "MC"))
uu[:] = np.ones((1, 20, 31), "f")
uu.long_name = "U on staggered points"
f.close()
o = sf.read_field(pstag, varname="UU", max_points=60)
assert o["on_index"] is True, "champ decale -> trace sur les indices"
assert "décalé" in o.get("note", ""), o.get("note")
assert o["n_x"] == 31 and o["n_y"] == 20

print("OK — détection des variables, réduction temporelle, "
      "sous-échantillonnage, transposition, ré-échantillonnage curviligne "
      "et erreurs explicites validés.")
# ══════════════════════════════════════════════════════════════
# Structure reelle d'une sortie Delft3D-WAVE (SWAN)
#   x, y     (nmax, mmax) centres de mailles, coordonnees projetees
#   hsign, setup, period, dir, wlength, depth  (time, nmax, mmax)
# ══════════════════════════════════════════════════════════════

def write_wave(path, nmax=60, mmax=45, ntime=5, curvilinear=True):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", ntime)
    f.createDimension("nmax", nmax)
    f.createDimension("mmax", mmax)

    i, j = np.meshgrid(np.linspace(0, 1, mmax), np.linspace(0, 1, nmax))
    if curvilinear:
        ang = np.deg2rad(12.0)
        xx = 250000 + (i * np.cos(ang) - j * np.sin(ang)) * 60000
        yy = 6800000 + (i * np.sin(ang) + j * np.cos(ang)) * 50000
    else:                                  # grille reguliere ecrite en 2D
        xx = 250000 + i * 60000
        yy = 6800000 + j * 50000
    xv = f.createVariable("x", "f", ("nmax", "mmax")); xv[:] = xx.astype("f")
    yv = f.createVariable("y", "f", ("nmax", "mmax")); yv[:] = yy.astype("f")

    spec = [("depth", "m", "Water depth", 3.0),
            ("period", "sec", "Mean wave period", 4.0),
            ("dir", "deg", "Mean wave direction", 90.0),
            ("setup", "m", "Set-up due to waves", 0.05),
            ("hsign", "m", "Significant wave height", 0.8),
            ("wlength", "m", "Mean wave length", 12.0)]
    for name, unit, label, amp in spec:
        v = f.createVariable(name, "f", ("time", "nmax", "mmax"))
        for t in range(ntime):
            v[t] = (amp * (t + 1) / ntime * i).astype("f")
        v.units = unit
        v.long_name = label
    f.close()


pw = TMP / "wave.nc"
write_wave(pw)

ds = sf.open_dataset(pw)
info = sf.describe_dataset(ds)
ds.close()
assert info["x"] == "x" and info["y"] == "y", info
assert info["coord_shape"] == (60, 45)
assert len(info["fields"]) == 6
assert all(f["on_coords"] for f in info["fields"])

# Le champ propose par defaut doit etre Hs, pas setup ni depth
o = sf.read_field(pw, max_points=200)
assert o["var"] == "hsign", f"défaut attendu hsign, obtenu {o['var']}"
assert o["label"] == "Significant wave height"
assert o["units"] == "m"
assert abs(o["zmax"] - 0.8) < 0.02, o["zmax"]     # dernier pas de temps
assert any("time" in n for n in o["reduction"])

# Ordre de priorite complet
ranks = {f["name"]: sf.field_priority(f) for f in info["fields"]}
order = sorted(ranks, key=lambda k: ranks[k])
assert order[0] == "hsign", order
assert order.index("setup") < order.index("depth"), order

# Grille curviligne -> re-echantillonnage, coordonnees projetees
assert o["regridded"] is True
assert o["x"][0] > 100000 and o["y"][0] > 1000000

# ── Grille reguliere ecrite en 2D : pas de triangulation ─────
pr = TMP / "wave_rect.nc"
write_wave(pr, curvilinear=False)
o2 = sf.read_field(pr, max_points=200)
assert o2["regridded"] is False, "grille régulière : axes déduits directement"
assert o2["n_x"] == 45 and o2["n_y"] == 60, "résolution native conservée"
assert abs(o2["zmax"] - 0.8) < 0.02

# rectilinear_axes : detection unitaire
i, j = np.meshgrid(np.linspace(0, 1, 5), np.linspace(0, 1, 4))
assert sf.rectilinear_axes(250000 + i * 10, 6800000 + j * 10) is not None
rot = np.deg2rad(20)
assert sf.rectilinear_axes(i * np.cos(rot) - j * np.sin(rot),
                           i * np.sin(rot) + j * np.cos(rot)) is None
# Coordonnees masquees (cellules inactives) -> interpolation
xnan = (250000 + i * 10).copy(); xnan[0, 0] = np.nan
assert sf.rectilinear_axes(xnan, 6800000 + j * 10) is None

print("OK — structure Delft3D-FLOW : couches verticales, constituants, "
      "coordonnées projetées et grille décalée validés.")
# ══════════════════════════════════════════════════════════════
# Cellules hors domaine : sentinelles Delft3D dans les coordonnees
#   FLOW : 0 et -999.999      WAVE : valeur de remplissage ~9.97e36
# Sans nettoyage, l'emprise du trace part de l'origine et le domaine
# reel est ecrase dans un coin.
# ══════════════════════════════════════════════════════════════

def write_with_sentinels(path, sentinel, nn=40, nm=30, active=0.5):
    """Grille projetee dont une partie des cellules est hors domaine."""
    f = netcdf_file(str(path), "w")
    f.createDimension("time", 2); f.createDimension("N", nn)
    f.createDimension("M", nm)
    i, j = np.meshgrid(np.linspace(0, 1, nm), np.linspace(0, 1, nn))
    xx = 500000 + i * 100000        # 500 km -> 600 km
    yy = 6800000 + j * 80000        # 6800 km -> 6880 km
    z = (1.0 + i).astype("f")

    off = np.zeros((nn, nm), bool)
    off[: int(nn * (1 - active)), :] = True     # moitie haute hors domaine
    xx[off] = sentinel; yy[off] = sentinel
    z[off] = 0.0                                # le champ aussi vaut 0

    xv = f.createVariable("XZ", "f8", ("N", "M")); xv[:] = xx
    yv = f.createVariable("YZ", "f8", ("N", "M")); yv[:] = yy
    v = f.createVariable("S1", "f", ("time", "N", "M"))
    v[0] = z; v[1] = z
    v.units = "m"; v.long_name = "Water-level in zeta point"
    f.close()
    return xx, yy


for sentinel, label in [(0.0, "zéro"), (-999.999, "-999.999"),
                        (9.96921e36, "remplissage NetCDF")]:
    ps = TMP / f"sent_{abs(sentinel):.0f}.nc"
    write_with_sentinels(ps, sentinel)
    o = sf.read_field(ps, max_points=80)

    # L'emprise doit couvrir le domaine reel, pas partir de l'origine
    assert o["x"][0] > 400000, f"{label} : emprise x démarre à {o['x'][0]}"
    assert o["y"][0] > 6000000, f"{label} : emprise y démarre à {o['y'][0]}"
    assert o["x"][-1] <= 600001 and o["y"][-1] <= 6880001
    # Les cellules hors domaine sont comptees
    assert o["n_valid_cells"] < o["n_cells"], label
    assert o["n_valid_cells"] == 20 * 30, (label, o["n_valid_cells"])
    assert o["coords"] == "XZ/YZ"
    # Le champ ne doit plus contenir les zeros des cellules mortes
    assert o["zmin"] is not None and o["zmin"] >= 0.9, (label, o["zmin"])

# ── clean_coords : cas unitaires ─────────────────────────────
x = np.array([[500000.0, 0.0], [-999.999, 9.96921e36]])
y = np.array([[6800000.0, 10.0], [20.0, 30.0]])
cx, cy, nv, nt = sf.clean_coords(x, y)
assert nv == 1 and nt == 4
assert np.isfinite(cx[0, 0]) and not np.isfinite(cx[0, 1])
assert not np.isfinite(cx[1, 0]) and not np.isfinite(cx[1, 1])

# En lon/lat, 0 reste une valeur legitime (meridien de Greenwich)
lon = np.array([[0.0, 1.5], [2.0, 3.0]])
lat = np.array([[51.0, 51.5], [52.0, 52.5]])
_, _, nv2, nt2 = sf.clean_coords(lon, lat)
assert nv2 == 4, "0 ne doit pas etre traite en sentinelle en degres"

# ── Repli sur XCOR/YCOR si XZ/YZ sont vides ──────────────────
pfb = TMP / "fallback.nc"
f = netcdf_file(str(pfb), "w")
f.createDimension("N", 20); f.createDimension("M", 15)
i, j = np.meshgrid(np.linspace(0, 1, 15), np.linspace(0, 1, 20))
xz = f.createVariable("XZ", "f8", ("N", "M")); xz[:] = np.zeros((20, 15))
yz = f.createVariable("YZ", "f8", ("N", "M")); yz[:] = np.zeros((20, 15))
xc = f.createVariable("XCOR", "f8", ("N", "M")); xc[:] = 500000 + i * 1000
yc = f.createVariable("YCOR", "f8", ("N", "M")); yc[:] = 6800000 + j * 1000
v = f.createVariable("S1", "f", ("N", "M")); v[:] = (1 + i).astype("f")
f.close()
o = sf.read_field(pfb, varname="S1", max_points=60)
assert o["coords"] == "XCOR/YCOR", o.get("coords")
assert o["x"][0] > 400000

print("OK — structure Delft3D-WAVE : hsign proposé par défaut, "
      "grille régulière 2D détectée sans interpolation.")
print("OK — sentinelles Delft3D (0, -999.999, remplissage) écartées, "
      "emprise du tracé correcte et repli XCOR/YCOR validés.")

# ══════════════════════════════════════════════════════════════
# Masquage des zeros et champ de vecteurs (quiver)
# ══════════════════════════════════════════════════════════════

def write_currents(path, nn=40, nm=30, nlay=4, rot_deg=25.0):
    """Grille tournee avec une zone seche (U = V = 0)."""
    f = netcdf_file(str(path), "w")
    f.createDimension("time", 3); f.createDimension("KMAXOUT_RESTR", nlay)
    f.createDimension("N", nn); f.createDimension("M", nm)
    i, j = np.meshgrid(np.linspace(0, 1, nm), np.linspace(0, 1, nn))
    a = np.deg2rad(rot_deg)
    # Rotation pure : meme echelle sur les deux axes, sinon l'angle de
    # l'axe ksi n'est plus celui de la rotation.
    xx = 600000 + (i * np.cos(a) - j * np.sin(a)) * 50000
    yy = 6800000 + (i * np.sin(a) + j * np.cos(a)) * 50000
    xv = f.createVariable("XZ", "f8", ("N", "M")); xv[:] = xx
    yv = f.createVariable("YZ", "f8", ("N", "M")); yv[:] = yy

    dry = j > 0.75                       # quart superieur sec
    u = np.where(dry, 0.0, 0.30)         # ksi
    v = np.where(dry, 0.0, 0.00)         # eta
    uu = f.createVariable("U1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    vv = f.createVariable("V1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    for t in range(3):
        for k in range(nlay):
            uu[t, k] = u.astype("f"); vv[t, k] = v.astype("f")
    uu.units = "m/s"; uu.location = "edge1"
    uu.long_name = "U-velocity per layer in U-point (Eulerian)"
    vv.units = "m/s"; vv.location = "edge2"
    f.close()


pc2 = TMP / "currents.nc"
write_currents(pc2)

# ── Masquage des zeros ───────────────────────────────────────
assert sf.should_mask_zero("U1", "auto") and sf.should_mask_zero("TAUMAX", "auto")
assert not sf.should_mask_zero("S1", "auto")
assert sf.should_mask_zero("S1", True) and not sf.should_mask_zero("U1", False)

o = sf.read_field(pc2, varname="U1", max_points=60, mask_zero="auto")
flat = [v for row in o["z"] for v in row if v is not None]
assert flat, "le champ ne doit pas etre entierement masque"
assert min(flat) > 0.0, f"les zeros des cellules seches subsistent ({min(flat)})"

o0 = sf.read_field(pc2, varname="U1", max_points=60, mask_zero=False)
flat0 = [v for row in o0["z"] for v in row if v is not None]
assert min(flat0) == 0.0, "sans masquage, les zeros doivent rester"

# ── Carte de courants ────────────────────────────────────────
c = sf.read_currents(pc2, n_arrows=12, grid_res=40)
v = dict(c["arrows"]); v.update({k: c[k] for k in
        ("u_var", "v_var", "units", "rotated", "n_arrows")})
v["speed_max"] = c["zmax"]

# Champ d'intensite en fond : NaN hors domaine, valeurs > 0 ailleurs
zf = [t for row in c["speed"]["z"] for t in row if t is not None]
assert zf and min(zf) > 0, "les valeurs nulles doivent etre transparentes"
assert any(t is None for row in c["speed"]["z"] for t in row), \
    "la zone seche doit rester transparente"
assert c["n_x"] == 40 and c["n_y"] == 40

# Lissage gaussien insensible aux NaN
csm = sf.read_currents(pc2, n_arrows=12, grid_res=40, smooth=2.0)
assert csm["smooth"] == 2.0
nan_before = sum(1 for row in c["speed"]["z"] for t in row if t is None)
nan_after = sum(1 for row in csm["speed"]["z"] for t in row if t is None)
assert nan_after == nan_before, "le lissage ne doit pas ronger le domaine"

assert v["n_arrows"] > 0
assert v["u_var"] == "U1" and v["v_var"] == "V1"
assert v["units"] == "m/s"
assert abs(v["speed_max"] - 0.30) < 0.02, v["speed_max"]
# Aucune fleche de vitesse nulle
assert all(abs(a) + abs(b) > 0 for a, b in zip(v["u"], v["v"]))
assert min(v["speed"]) > 0

# Rotation : U1 est porte par ksi ; sur une grille tournee de 25 deg,
# les composantes x/y doivent refleter cet angle.
ang = np.degrees(np.arctan2(np.mean(v["v"]), np.mean(v["u"])))
assert v["rotated"] is True
assert abs(ang - 25.0) < 3.0, f"angle obtenu {ang:.1f} deg au lieu de 25"

craw = sf.read_currents(pc2, n_arrows=12, grid_res=30, rotate=False)
vraw = dict(craw["arrows"]); vraw["rotated"] = craw["rotated"]
assert vraw["rotated"] is False
ang_raw = np.degrees(np.arctan2(np.mean(vraw["v"]), np.mean(vraw["u"])))
assert abs(ang_raw) < 1.0, "sans rotation, le vecteur reste selon ksi"

# Les fleches restent dans l'emprise du domaine
assert min(v["x"]) > 500000 and min(v["y"]) > 6000000
# Choix de la couche
c2 = sf.read_currents(pc2, n_arrows=8, grid_res=30, layer_index=3)
assert c2["n_arrows"] > 0

# ══════════════════════════════════════════════════════════════
# Contour du lac : les mailles seches doivent rester DANS le jeu de
# points d'interpolation (intensite nulle), sans quoi l'interpolation
# lineaire remplit l'enveloppe convexe du domaine et le lac disparait
# sous un aplat triangule.
# ══════════════════════════════════════════════════════════════

def write_lake(path, nn=90, nm=70, nlay=4):
    """Domaine rectangulaire dont seule une ellipse est en eau."""
    f = netcdf_file(str(path), "w")
    f.createDimension("time", 3); f.createDimension("KMAXOUT_RESTR", nlay)
    f.createDimension("N", nn); f.createDimension("M", nm)
    i, j = np.meshgrid(np.linspace(0, 1, nm), np.linspace(0, 1, nn))
    xv = f.createVariable("XZ", "f8", ("N", "M"))
    yv = f.createVariable("YZ", "f8", ("N", "M"))
    xv[:] = 680000 + i * 100000
    yv[:] = 6780000 + j * 120000
    lake = ((i - 0.5) / 0.25) ** 2 + ((j - 0.5) / 0.38) ** 2 <= 1
    u = f.createVariable("U1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    v = f.createVariable("V1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    for t in range(3):
        for k in range(nlay):
            u[t, k] = np.where(lake, 0.22, 0.0).astype("f")
            v[t, k] = np.where(lake, 0.06, 0.0).astype("f")
    u.units = "m/s"; u.location = "edge1"
    u.long_name = "U-velocity per layer in U-point (Eulerian)"
    v.units = "m/s"; v.location = "edge2"
    f.close()
    return lake


pl = TMP / "lake.nc"
lake_mask = write_lake(pl)
cl = sf.read_currents(pl, n_arrows=24, grid_res=120, smooth=0.0,
                      vmin=0.0, vmax=0.5)

zl = np.array([[np.nan if t is None else t for t in row]
               for row in cl["speed"]["z"]])
wet_fraction = np.isfinite(zl).mean()
lake_fraction = lake_mask.mean()
assert abs(wet_fraction - lake_fraction) < 0.07, (
    f"le tracé doit épouser le lac ({lake_fraction:.2f}), "
    f"obtenu {wet_fraction:.2f}")
assert wet_fraction < 0.75, "l'enveloppe convexe ne doit pas être remplie"

# Les fleches restent dans le lac
gi = (np.array(cl["arrows"]["x"]) - 680000) / 100000
gj = (np.array(cl["arrows"]["y"]) - 6780000) / 120000
inside = ((gi - 0.5) / 0.25) ** 2 + ((gj - 0.5) / 0.38) ** 2 <= 1.1
assert inside.mean() > 0.95, "des flèches sont tracées hors de l'eau"

# Bornes de couleur transmises telles quelles
assert cl["vmin"] == 0.0 and cl["vmax"] == 0.5

# Emprise imposee
cb = sf.read_currents(pl, n_arrows=10, grid_res=60,
                      bounds=(700000, 760000, 6800000, 6870000))
assert cb["speed"]["x"][0] >= 700000 and cb["speed"]["x"][-1] <= 760000
assert cb["speed"]["y"][0] >= 6800000 and cb["speed"]["y"][-1] <= 6870000

try:
    sf.read_currents(pl, bounds=(0, 1, 0, 1))
    raise AssertionError("une emprise hors domaine doit lever une erreur")
except ValueError as e:
    assert "bounds" in str(e).lower()

print("OK — masquage des zeros et champ de vecteurs (rotation vers x/y, "
      "cellules seches ecartees) validés.")
print("OK — contour du lac préservé, flèches confinées à l'eau, bornes "
      "de couleur et emprise imposée validées.")

# ══════════════════════════════════════════════════════════════
# Couches cartographiques : aucun debordement hors du lac, quelle que
# soit la convention utilisee pour les mailles seches (0 cote FLOW,
# valeur manquante cote WAVE).
# ══════════════════════════════════════════════════════════════

import geo as _geo  # noqa: E402


def write_map_case(path, dry_value, nn=110, nm=85):
    """Domaine large, lac ellipsoidal ; hors du lac : dry_value."""
    f = netcdf_file(str(path), "w")
    f.createDimension("time", 4); f.createDimension("nmax", nn)
    f.createDimension("mmax", nm)
    i, j = np.meshgrid(np.linspace(0, 1, nm), np.linspace(0, 1, nn))
    xx = 673229 + i * 124425
    yy = 6778805 + j * 146008
    lake = ((i - 0.45) / 0.26) ** 2 + ((j - 0.5) / 0.40) ** 2 <= 1
    xv = f.createVariable("x", "f8", ("nmax", "mmax")); xv[:] = xx
    yv = f.createVariable("y", "f8", ("nmax", "mmax")); yv[:] = yy
    hs = f.createVariable("hsign", "f", ("time", "nmax", "mmax"))
    dr = f.createVariable("dir", "f", ("time", "nmax", "mmax"))
    for t in range(4):
        hs[t] = np.where(lake, 0.4 + 0.5 * i, dry_value).astype("f")
        dr[t] = np.where(lake, 315.0, dry_value).astype("f")
    hs.units = "m"; hs.long_name = "Significant wave height"
    dr.units = "deg"; dr.long_name = "Mean wave direction"
    f.close()
    return lake


for dry, label in [(0.0, "zéro"), (np.nan, "valeur manquante")]:
    pm = TMP / f"map_{'zero' if dry == 0 else 'nan'}.nc"
    lake = write_map_case(pm, dry)
    d = sf.read_map_layer(pm, layer="hsign", zone=53, grid_res=180,
                          n_arrows=28, smooth=0.0)

    zz = np.array([[np.nan if t is None else t for t in row] for row in d["z"]])
    frac = np.isfinite(zz).mean()
    assert abs(frac - lake.mean()) < 0.07, (
        f"{label} : raster {frac:.2f} pour un lac a {lake.mean():.2f}")

    ax_, ay_ = _geo.lonlat_to_utm_array(np.array(d["arrows"]["lon"]),
                                        np.array(d["arrows"]["lat"]), 53)
    ii = (ax_ - 673229) / 124425
    jj = (ay_ - 6778805) / 146008
    inside = ((ii - 0.45) / 0.26) ** 2 + ((jj - 0.5) / 0.40) ** 2 <= 1.08
    assert inside.mean() > 0.97, f"{label} : {inside.mean():.2%} de flèches dans l'eau"
    assert d["n_arrows"] > 20

    # Direction des vagues : convention nautique -> propagation +180
    assert abs(np.mean(d["arrows"]["bearing"]) - 135.0) < 1.0
    d_to = sf.read_map_layer(pm, layer="hsign", zone=53, grid_res=60,
                             n_arrows=10, wave_dir_convention="to")
    assert abs(np.mean(d_to["arrows"]["bearing"]) - 315.0) < 1.0

    # Emprise geographique et calage a la demi-maille
    (lat0, lon0), (lat1, lon1) = d["bounds"]
    assert 136 < lon0 < 139 and -30 < lat0 < -27
    dlat = (d["lat"][-1] - d["lat"][0]) / (len(d["lat"]) - 1)
    assert abs(lat0 - (d["lat"][0] - dlat / 2)) < 1e-5

# ══════════════════════════════════════════════════════════════
# Lac calme : courants nuls mais eau presente.
#
# Sans masque explicite, « valeur > 0 » confond une eau calme avec une
# maille seche et la couche apparait vide — c'est exactement ce qui se
# produisait sur les scenarios a vent faible.
# ══════════════════════════════════════════════════════════════

ci, cj = np.meshgrid(np.linspace(0, 1, 70), np.linspace(0, 1, 90))
clon = (136.98 + ci * 0.72).ravel()
clat = (-28.99 + cj * 1.10).ravel()
clake = ((((ci - 0.45) / 0.28) ** 2 + ((cj - 0.5) / 0.40) ** 2) <= 1).ravel()
cspec = sf.MAP_LAYERS["currents"]
zero = np.zeros(clon.size)

# Sans masque : le lac disparaît (comportement à corriger)
try:
    sf.assemble_map(clon, clat, zero, cspec,
                    extra={"ue": zero, "vn": zero},
                    grid_res=60, n_arrows=12, smooth=0.0)
    raise AssertionError("sans masque, un champ nul devrait être signalé")
except ValueError as e:
    assert "wet" in str(e).lower(), e

# Avec masque : le lac reste affiché
out = sf.assemble_map(clon, clat, zero, cspec,
                      extra={"ue": zero, "vn": zero}, wet=clake,
                      grid_res=60, n_arrows=12, smooth=0.0)
zc = np.array([[np.nan if t is None else t for t in r] for r in out["z"]])
assert abs(np.isfinite(zc).mean() - clake.mean()) < 0.08, (
    f"lac calme : {np.isfinite(zc).mean():.2f} coloré pour "
    f"{clake.mean():.2f} d'eau")
assert out["masked"] is True and out["n_wet"] == int(clake.sum())
assert out["n_arrows"] == 0, "aucune flèche si la vitesse est nulle partout"
assert out["zmax"] == 0.0

# Courants très faibles : visibles, avec flèches
tiny_u = np.where(clake, 0.0008, 0.0)
out = sf.assemble_map(clon, clat, np.abs(tiny_u), cspec,
                      extra={"ue": tiny_u, "vn": zero}, wet=clake,
                      grid_res=60, n_arrows=12, smooth=0.0)
assert np.isfinite(np.array([[np.nan if t is None else t for t in r]
                             for r in out["z"]])).mean() > 0.25
assert out["n_arrows"] > 0 and out["zmax"] > 0

# Le masque prime sur la valeur : une maille en eau à zéro reste colorée,
# une maille sèche à valeur non nulle reste transparente.
odd = np.where(clake, 0.0, 0.5)          # valeurs uniquement hors du lac
out = sf.assemble_map(clon, clat, odd, cspec,
                      extra={"ue": odd, "vn": zero}, wet=clake,
                      grid_res=60, n_arrows=12, smooth=0.0)
zo = np.array([[np.nan if t is None else t for t in r] for r in out["z"]])
assert abs(np.isfinite(zo).mean() - clake.mean()) < 0.08, (
    "le masque doit primer sur la valeur")

# ── wet_mask : dérivation depuis le niveau d'eau ─────────────
pw2 = TMP / "wetmask.nc"
f = netcdf_file(str(pw2), "w")
f.createDimension("time", 2); f.createDimension("N", 20); f.createDimension("M", 15)
gi2, gj2 = np.meshgrid(np.linspace(0, 1, 15), np.linspace(0, 1, 20))
lk = ((gi2 - 0.5) ** 2 + (gj2 - 0.5) ** 2) <= 0.16
s1 = f.createVariable("S1", "f", ("time", "N", "M"))
for t in range(2):
    s1[t] = np.where(lk, -13.0, 0.0).astype("f")   # 0 hors de l'eau
f.close()
ds2 = sf.open_dataset(pw2)
mask = sf.wet_mask(ds2, "S1", -1)
ds2.close()
assert mask is not None and mask.sum() == int(lk.sum()), (mask.sum(), lk.sum())

ds3 = sf.open_dataset(pw2)
assert sf.wet_mask(ds3, "absente", -1) is None, "variable absente -> None"
ds3.close()

print("OK — couches cartographiques : pas de débordement hors du lac "
      "(mailles sèches à 0 comme en valeur manquante), flèches et "
      "emprise géographique correctes.")
# ══════════════════════════════════════════════════════════════
# Aucune valeur non finie dans la charge utile.
#
# Le masque est calcule au plus proche voisin (defini partout) alors
# que l'intensite vient d'une interpolation lineaire (NaN hors de
# l'enveloppe convexe). Sur un domaine non convexe, une fleche peut
# donc tomber la ou l'intensite vaut NaN : le JSON produit devient
# invalide et le navigateur rejette toute la reponse.
# ══════════════════════════════════════════════════════════════

import json as _json  # noqa: E402


def _strict(c):
    raise ValueError("constante JSON interdite : " + c)


# Grille TOURNEE, comme la grille curviligne reprojetee du modele :
# les coins de l'emprise lon/lat tombent alors hors de l'enveloppe
# convexe des points sources, la ou l'interpolation lineaire vaut NaN
# tandis que le masque au plus proche voisin reste defini.
li_, lj_ = np.meshgrid(np.linspace(0, 1, 60), np.linspace(0, 1, 60))
_ang = np.deg2rad(25.0)
_x = 673229 + (li_ * np.cos(_ang) - lj_ * np.sin(_ang)) * 120000
_y = 6778805 + (li_ * np.sin(_ang) + lj_ * np.cos(_ang)) * 120000
llon, llat = [], []
for _cx, _cy in zip(_x.ravel(), _y.ravel()):
    _lo, _la = _geo.utm_to_lonlat(float(_cx), float(_cy), 53)
    llon.append(_lo); llat.append(_la)
llon = np.array(llon); llat = np.array(llat)
# Le lac doit TOUCHER les bords du domaine : c'est la que le masque au
# plus proche voisin deborde l'enveloppe convexe. Un lac centre ne
# reproduirait pas le defaut.
llake = (li_ > 0.15).ravel()

lue = np.where(llake, 0.12, 0.0)
lvn = np.where(llake, 0.03, 0.0)

for label, spec_, extra_, vals_ in [
    ("currents", sf.MAP_LAYERS["currents"],
     {"ue": lue, "vn": lvn}, np.hypot(lue, lvn)),
    ("hsign", sf.MAP_LAYERS["hsign"],
     {"dir": np.where(llake, 315.0, 0.0)}, np.where(llake, 0.6, 0.0)),
]:
    payload = sf.assemble_map(llon, llat, vals_, spec_, extra=extra_,
                              wet=llake, grid_res=80, n_arrows=20,
                              smooth=0.0)
    for field in ("lat", "lon", "bearing", "value"):
        bad = [v for v in payload["arrows"][field] if not np.isfinite(v)]
        assert not bad, f"{label} : {len(bad)} valeur(s) non finie(s) dans " \
                        f"arrows.{field}"
    # Contrôle décisif : un parseur strict, comme celui du navigateur
    _json.loads(_json.dumps(payload), parse_constant=_strict)
    assert payload["n_arrows"] > 0, label

print("OK — lac calme : le masque explicite distingue eau immobile et "
      "maille sèche ; wet_mask dérivé du niveau d'eau validé.")
print("OK — charge utile sans valeur non finie, acceptée par un parseur "
      "JSON strict (domaine non convexe).")
