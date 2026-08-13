#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du fichier compact (pipeline/compact.py et compact_store.py).

netCDF4 n'etant pas requis ici, le fichier compact est ecrit et relu
avec scipy.io.netcdf_file, et le facteur d'echelle est applique par le
magasin lui-meme — c'est precisement pour cela qu'il ne s'appuie pas
sur la mise a l'echelle automatique de netCDF4.

Verifie :
  - l'encodage entier 16 bits : precision et ecretage ;
  - la restitution des champs a travers le magasin ;
  - la selection de couche ;
  - qu'une couche produite depuis le fichier compact est equivalente a
    celle produite en lisant les NetCDF d'origine ;
  - le rejet propre d'un scenario absent.

Execution :  python tests/test_compact.py
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import compact  # noqa: E402
import compact_store  # noqa: E402
import scenario_field as sf  # noqa: E402

TMP = Path(tempfile.mkdtemp())

# ── Encodage entier 16 bits ──────────────────────────────────
vals = np.array([0.0, 0.0001, 0.25, -0.4, 1.2345])
packed = compact.pack(vals, 1e-4)
back = packed.astype("float64") * 1e-4
assert np.allclose(back, vals, atol=5e-5), back
assert packed.dtype == np.int16

# Ecretage plutot que debordement silencieux
huge = compact.pack(np.array([1e6]), 1e-4)
assert huge[0] == 32767, huge

# Precision suffisante pour chaque champ
for scale, amplitude, name in [(1e-4, 0.5, "vitesse"), (1e-4, 2.0, "hsign"),
                               (1e-2, 60.0, "wlength"), (1e-3, 12.0, "period"),
                               (2e-2, 359.9, "dir")]:
    a = np.linspace(0, amplitude, 500)
    b = compact.pack(a, scale).astype("float64") * scale
    assert np.abs(a - b).max() <= scale, (name, np.abs(a - b).max())
    assert compact.pack(np.array([amplitude]), scale)[0] < 32767, \
        f"{name} : l'amplitude maximale doit tenir dans un entier 16 bits"

# ── Fichier compact synthetique ──────────────────────────────
NC = 400
KEYS = ["wind-sp6.0_wind-dir135.0_wlvl-13.0_sal150.0",
        "wind-sp20.0_wind-dir270.0_wlvl-11.0_sal250.0"]
NLAY = 3

i = np.linspace(0, 1, 20)
j = np.linspace(0, 1, 20)
gi, gj = np.meshgrid(i, j)
lon_all = (136.98 + gi * 0.72).ravel()
lat_all = (-28.99 + gj * 1.10).ravel()
lake = ((((gi - 0.5) / 0.30) ** 2 + ((gj - 0.5) / 0.40) ** 2) <= 1).ravel()
NC = lon_all.size

path = TMP / "compact.nc"
f = netcdf_file(str(path), "w")
f.createDimension("scenario", len(KEYS))
f.createDimension("layer", NLAY)
f.createDimension("flow_cell", NC)
f.createDimension("wave_cell", NC)
f.utm_zone = 53
f.time_index = -1
for src in ("flow", "wave"):
    v = f.createVariable(f"{src}_lon", "f8", (f"{src}_cell",)); v[:] = lon_all
    v = f.createVariable(f"{src}_lat", "f8", (f"{src}_cell",)); v[:] = lat_all

ue = f.createVariable("flow_ue", "i2", ("scenario", "layer", "flow_cell"))
vn = f.createVariable("flow_vn", "i2", ("scenario", "layer", "flow_cell"))
ue.scale_factor = 1e-4
vn.scale_factor = 1e-4
for n in range(len(KEYS)):
    for k in range(NLAY):
        speed = (0.30 - 0.08 * k) * (1 + 0.5 * n)
        ue[n, k] = compact.pack(np.where(lake, speed, 0.0), 1e-4)
        vn[n, k] = compact.pack(np.where(lake, 0.0, 0.0), 1e-4)

for name, scale, amp in [("wave_hsign", 1e-4, 0.8), ("wave_wlength", 1e-2, 14.0),
                         ("wave_period", 1e-3, 3.5), ("wave_dir", 2e-2, 315.0)]:
    v = f.createVariable(name, "i2", ("scenario", "wave_cell"))
    v.scale_factor = scale
    for n in range(len(KEYS)):
        v[n] = compact.pack(np.where(lake, amp, 0.0), scale)
f.close()


def make_store():
    """scipy n'ecrit pas de variables de chaines : les cles sont
    injectees, le reste est lu depuis le fichier."""
    store = object.__new__(compact_store.CompactStore)
    store.path = path
    store._open = lambda p: netcdf_file(str(p), "r", mmap=False)
    store.ds = store._open(path)
    store.keys = list(KEYS)
    store.index = {k: n for n, k in enumerate(KEYS)}
    store.zone = 53
    store.layers = [0, 4, 9][:NLAY]
    store.ds.n_layers_source = 10
    store.time_index = -1
    store.coords = {}
    for src in ("flow", "wave"):
        store.coords[src] = (
            np.asarray(store.ds.variables[f"{src}_lon"][:], dtype="f8"),
            np.asarray(store.ds.variables[f"{src}_lat"][:], dtype="f8"))
    return store


store = make_store()
assert store.has(KEYS[0]) and not store.has("inconnu")

# ── Courants : couche et scenario ────────────────────────────
d0 = store.map_layer(KEYS[0], layer="currents", layer_index=0,
                     grid_res=60, n_arrows=14, smooth=0.0)
assert d0["source"] == "compact"
assert abs(d0["zmax"] - 0.30) < 0.01, d0["zmax"]
assert d0["n_arrows"] > 10
# u vers l'est, v nul -> azimut 90 deg
assert abs(np.mean(d0["arrows"]["bearing"]) - 90.0) < 1.0

d2 = store.map_layer(KEYS[0], layer="currents", layer_index=2,
                     grid_res=60, n_arrows=10, smooth=0.0)
assert abs(d2["zmax"] - 0.14) < 0.01, d2["zmax"]
ax = d2["axes"][0]
assert ax["index"] == 2 and ax["size"] == NLAY
# La numerotation d'origine doit survivre au compactage : la 3e couche
# conservee est la 10e du modele, pas la 3e.
assert ax["values"] == [1, 5, 10], ax["values"]
assert ax["total"] == 10

d_hi = store.map_layer(KEYS[1], layer="currents", layer_index=0,
                       grid_res=60, n_arrows=10, smooth=0.0)
assert abs(d_hi["zmax"] - 0.45) < 0.02, d_hi["zmax"]

# Indice de couche hors bornes : borne au maximum plutot qu'erreur
d_cl = store.map_layer(KEYS[0], layer="currents", layer_index=99,
                       grid_res=40, n_arrows=8, smooth=0.0)
assert d_cl["axes"][0]["index"] == NLAY - 1

# ── Vagues ───────────────────────────────────────────────────
w = store.map_layer(KEYS[0], layer="hsign", grid_res=60, n_arrows=14,
                    smooth=0.0)
assert abs(w["zmax"] - 0.8) < 0.01, w["zmax"]
assert abs(np.mean(w["arrows"]["bearing"]) - 135.0) < 1.0, "convention nautique"
assert w["units"] == "m" and w["label"] == "Wave height"

for lay, expected in [("wlength", 14.0), ("period", 3.5)]:
    o = store.map_layer(KEYS[0], layer=lay, grid_res=40, n_arrows=8,
                        smooth=0.0)
    assert abs(o["zmax"] - expected) < max(0.05, expected * 0.01), (lay, o["zmax"])

# ── Le contour du lac est conserve ───────────────────────────
z = np.array([[np.nan if t is None else t for t in row] for row in w["z"]])
frac = np.isfinite(z).mean()
lake_frac = lake.reshape(20, 20).mean()
assert abs(frac - lake_frac) < 0.10, (frac, lake_frac)

# ── Scenario absent ──────────────────────────────────────────
try:
    store.map_layer("inconnu", layer="currents")
    raise AssertionError("un scénario absent doit lever une erreur")
except ValueError as e:
    assert "absent" in str(e)

# ── Couche inconnue ──────────────────────────────────────────
try:
    store.map_layer(KEYS[0], layer="temperature")
    raise AssertionError("une couche inconnue doit lever une erreur")
except ValueError as e:
    assert "Unknown map layer" in str(e)

store.close()

print("OK — encodage 16 bits (précision et écrêtage), restitution des "
      "champs, sélection de couche, contour du lac et rejets validés.")

# ══════════════════════════════════════════════════════════════
# Robustesse : indices hors bornes et runs heterogenes
#
# Sur 790 simulations, certaines n'ont pas le meme nombre de couches
# ou de pas de temps que les autres — un compactage de plusieurs
# heures ne doit pas s'arreter dessus.
# ══════════════════════════════════════════════════════════════


class FakeVar:
    def __init__(self, dims, shape):
        self.dimensions = dims
        self.shape = shape


CASES = [
    (("time", "KMAXOUT_RESTR", "N", "M"), (24, 10, 40, 30), "nominal"),
    (("time", "KMAXOUT_RESTR", "N", "M"), (24, 2, 40, 30), "2 couches"),
    (("time", "KMAXOUT_RESTR", "N", "M"), (1, 10, 40, 30), "1 pas de temps"),
    (("time", "KMAXOUT_RESTR", "N", "M"), (3, 1, 40, 30), "1 couche"),
    (("time", "N", "M"), (24, 40, 30), "sans couche"),
]
for dims, shape, label in CASES:
    for ti, li in [(-1, 9), (0, 0), (-30, 99), (23, 5)]:
        sl, _, _ = sf.build_slice(FakeVar(dims, shape), ti, li)
        for i, k in enumerate(sl):
            if isinstance(k, slice):
                continue
            assert -shape[i] <= k < shape[i], (label, dims[i], k, shape[i])

# Une dimension vide est signalee, pas silencieusement acceptee
try:
    sf.build_slice(FakeVar(("time", "N", "M"), (0, 40, 30)), -1, 0)
    raise AssertionError("une dimension vide doit lever une erreur")
except ValueError as e:
    assert "empty" in str(e)

# ── Le magasin signale une tranche vide (scénario en échec) ──
empty_path = TMP / "compact_empty.nc"
f = netcdf_file(str(empty_path), "w")
f.createDimension("scenario", 2); f.createDimension("layer", 1)
f.createDimension("flow_cell", NC); f.createDimension("wave_cell", NC)
f.utm_zone = 53
for src in ("flow", "wave"):
    v = f.createVariable(f"{src}_lon", "f8", (f"{src}_cell",)); v[:] = lon_all
    v = f.createVariable(f"{src}_lat", "f8", (f"{src}_cell",)); v[:] = lat_all
ue = f.createVariable("flow_ue", "i2", ("scenario", "layer", "flow_cell"))
vn = f.createVariable("flow_vn", "i2", ("scenario", "layer", "flow_cell"))
ue.scale_factor = 1e-4; vn.scale_factor = 1e-4
ue[0] = compact.pack(np.where(lake, 0.2, 0.0), 1e-4)   # rempli
vn[0] = compact.pack(np.zeros(NC), 1e-4)
# Scénario en échec : laissé entièrement en FILL
ue[1] = np.full(NC, compact.FILL, dtype="int16")
vn[1] = np.full(NC, compact.FILL, dtype="int16")
f.close()

store2 = object.__new__(compact_store.CompactStore)
store2.path = empty_path
store2._open = lambda p: netcdf_file(str(p), "r", mmap=False)
store2.ds = store2._open(empty_path)
store2.keys = ["plein", "vide"]
store2.index = {"plein": 0, "vide": 1}
store2.zone = 53; store2.layers = [0]; store2.time_index = -1
store2.coords = {s: (lon_all, lat_all) for s in ("flow", "wave")}

ok = store2.map_layer("plein", layer="currents", grid_res=40, n_arrows=8,
                      smooth=0.0)
assert ok["n_arrows"] > 0

try:
    store2.map_layer("vide", layer="currents", grid_res=40, n_arrows=8,
                     smooth=0.0)
    raise AssertionError("un run sans sortie FLOW doit être signalé pour "
                         "que le site retombe sur le NetCDF d'origine")
except ValueError as e:
    assert "no FLOW output" in str(e), e

# ── Eau calme : le lac reste affiché ─────────────────────────
# Un scénario à vent faible peut avoir des courants nuls partout ; les
# mailles restent en eau (valeur 0, pas FILL) et doivent s'afficher.
calm_path = TMP / "compact_calm.nc"
f = netcdf_file(str(calm_path), "w")
f.createDimension("scenario", 1); f.createDimension("layer", 1)
f.createDimension("flow_cell", NC)
v = f.createVariable("flow_lon", "f8", ("flow_cell",)); v[:] = lon_all
v = f.createVariable("flow_lat", "f8", ("flow_cell",)); v[:] = lat_all
ue2 = f.createVariable("flow_ue", "i2", ("scenario", "layer", "flow_cell"))
vn2 = f.createVariable("flow_vn", "i2", ("scenario", "layer", "flow_cell"))
ue2.scale_factor = 2e-4; vn2.scale_factor = 2e-4
ue2[0, 0] = np.where(lake, 0, compact.FILL).astype("int16")
vn2[0, 0] = np.where(lake, 0, compact.FILL).astype("int16")
f.close()

calm = object.__new__(compact_store.CompactStore)
calm.path = calm_path
calm._open = lambda p: netcdf_file(str(p), "r", mmap=False)
calm.ds = calm._open(calm_path)
calm.keys = ["calme"]; calm.index = {"calme": 0}
calm.zone = 53; calm.layers = [0]; calm.time_index = -1
calm.coords = {"flow": (lon_all, lat_all)}

out_calm = calm.map_layer("calme", layer="currents", grid_res=40,
                          n_arrows=8, smooth=0.0)
zc2 = np.array([[np.nan if t is None else t for t in r]
                for r in out_calm["z"]])
assert out_calm["masked"] is True
assert np.isfinite(zc2).mean() > 0.15, (
    "un lac calme doit rester affiché, pas disparaître")
assert out_calm["zmax"] == 0.0 and out_calm["n_arrows"] == 0
calm.close()
store2.close()

print("OK — indices bornés sur des runs hétérogènes, dimension vide "
      "signalée et tranche vide détectée par le magasin.")

# ══════════════════════════════════════════════════════════════
# Controle de l'archive : detection des runs incomplets
# ══════════════════════════════════════════════════════════════

import check_runs  # noqa: E402

check_runs.sfield.open_dataset = lambda p: netcdf_file(str(p), "r", mmap=False)

CHK = TMP / "archive"
(CHK / "F").mkdir(parents=True); (CHK / "W").mkdir(parents=True)


def _flow(path, ntime=24, nlay=10):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", ntime); f.createDimension("KMAXOUT_RESTR", nlay)
    f.createDimension("N", 12); f.createDimension("M", 9)
    for n in ("XZ", "YZ"):
        v = f.createVariable(n, "f8", ("N", "M")); v[:] = np.zeros((12, 9))
    for n in ("U1", "V1"):
        v = f.createVariable(n, "f", ("time", "KMAXOUT_RESTR", "N", "M"))
        for t in range(ntime):
            v[t] = np.zeros((nlay, 12, 9), "f")
    f.close()


def _wave(path, ntime=5, skip=None):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", ntime); f.createDimension("nmax", 12)
    f.createDimension("mmax", 9)
    for n in ("x", "y"):
        v = f.createVariable(n, "f8", ("nmax", "mmax")); v[:] = np.zeros((12, 9))
    for n in ("hsign", "wlength", "period", "dir"):
        if n == skip:
            continue
        v = f.createVariable(n, "f", ("time", "nmax", "mmax"))
        for t in range(ntime):
            v[t] = np.zeros((12, 9), "f")
    f.close()


scen_chk = []
for n in range(8):
    k = f"wind-sp{n + 1}.0_wind-dir0.0_wlvl-9.0_sal250.0"
    fp, wp = CHK / "F" / f"{k}.nc", CHK / "W" / f"wave_{k}.nc"
    if n == 3:
        _flow(fp, ntime=6)          # simulation interrompue
    elif n == 5:
        _flow(fp, nlay=1)           # une seule couche écrite
    else:
        _flow(fp)
    if n == 6:
        _wave(wp, ntime=1)
    elif n == 7:
        _wave(wp, skip="dir")       # variable manquante
    else:
        _wave(wp)
    scen_chk.append({"key": k, "params": {},
                     "files": {"flow": str(fp), "wave": str(wp)}})

reports = check_runs.scan(scen_chk, progress=False)
assert len(reports) == 8

ref_time = check_runs.majority_shape(reports, "flow", "n_time")
ref_lay = check_runs.majority_shape(reports, "flow", "n_layer")
assert ref_time == 24 and ref_lay == 10, (ref_time, ref_lay)
assert check_runs.majority_shape(reports, "wave", "n_time") == 5

# La variable manquante est vue directement
missing_var = [r for r in reports if any("dir" in p for p in r["problems"])]
assert len(missing_var) == 1 and missing_var[0]["key"].startswith("wind-sp8")

# Les structures minoritaires ressortent par comparaison
odd = []
for rec in reports:
    for source, info in rec["files"].items():
        for key, expected in (("n_time", check_runs.majority_shape(
                reports, source, "n_time")),
                ("n_layer", check_runs.majority_shape(
                    reports, source, "n_layer"))):
            got = info.get(key)
            if expected and got is not None and got != expected:
                odd.append((rec["key"], source, key, got, expected))

keys_odd = {k for k, *_ in odd}
assert any(k.startswith("wind-sp4") for k in keys_odd), "run tronqué non vu"
assert any(k.startswith("wind-sp6") for k in keys_odd), "couche manquante non vue"
assert any(k.startswith("wind-sp7") for k in keys_odd), "WAVE tronqué non vu"
assert not any(k.startswith("wind-sp1.") for k in keys_odd), "faux positif"

# Fichier absent et fichier illisible
broken = CHK / "F" / "broken.nc"
broken.write_bytes(b"pas un netcdf")
r = check_runs.scan([{"key": "cassé", "params": {},
                      "files": {"flow": str(broken),
                                "wave": str(CHK / "W" / "absent.nc")}}],
                    progress=False)[0]
assert any("illisible" in p for p in r["problems"]), r["problems"]
assert any("introuvable" in p for p in r["problems"]), r["problems"]

print("OK — contrôle de l'archive : runs tronqués, couches manquantes, "
      "variables absentes et fichiers illisibles détectés sans faux positif.")

# ══════════════════════════════════════════════════════════════
# Compactage complet de bout en bout.
#
# netCDF4 est indisponible ici : Dataset est remplace par un substitut
# en memoire. Ce test aurait attrape le bug ou build() appelait
# read_flow avec l'ancienne signature — la lecture des fichiers etait
# testee, l'assemblage ne l'etait pas.
# ══════════════════════════════════════════════════════════════

import json  # noqa: E402
import types  # noqa: E402


class MemVar:
    """Variable en memoire imitant netCDF4.Variable.

    Point essentiel : netCDF4 applique scale_factor AUTOMATIQUEMENT a
    l'ecriture (il divise) tant que set_auto_maskandscale(False) n'a
    pas ete appele. Ce substitut reproduit ce comportement — sans lui,
    un double encodage passerait inapercu dans les tests alors qu'il
    rend le fichier inutilisable.
    """

    def __init__(self, shape, dtype="f8"):
        self.shape = shape
        self.dtype = dtype
        self.data = np.zeros(shape, dtype=dtype) if shape else None
        self.attrs = {}
        self.autoscale = True

    @property
    def ndim(self):
        return len(self.shape) if self.shape else 1

    def __setitem__(self, k, v):
        if self.dtype == "str":          # variable de chaines (cles)
            self.data[k] = v
            return
        v = np.asarray(v, dtype="float64")
        if self.autoscale and "scale_factor" in self.attrs:
            v = v / self.attrs["scale_factor"]
        if self.dtype == "int16":
            # Debordement silencieux, comme le ferait netCDF4
            v = np.asarray(np.round(v)).astype("int64")
            v = ((v + 32768) % 65536) - 32768
        self.data[k] = v.astype(self.dtype)

    def __getitem__(self, k):
        raw = self.data[k]
        if self.autoscale and "scale_factor" in self.attrs:
            return raw.astype("float64") * self.attrs["scale_factor"]
        return raw

    def __setattr__(self, name, value):
        if name in ("shape", "dtype", "data", "attrs", "autoscale"):
            object.__setattr__(self, name, value)
        else:
            self.attrs[name] = value

    def set_auto_maskandscale(self, flag):
        object.__setattr__(self, "autoscale", bool(flag))


class MemDataset:
    """Substitut minimal de netCDF4.Dataset pour les tests."""

    instances = []

    def __init__(self, path, mode="w", format=None):
        object.__setattr__(self, "dimensions", {})
        object.__setattr__(self, "variables", {})
        object.__setattr__(self, "attrs", {})
        object.__setattr__(self, "path", str(path))
        object.__setattr__(self, "closed", False)
        MemDataset.instances.append(self)

    def __setattr__(self, name, value):
        self.attrs[name] = value

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "attrs")[name]
        except KeyError:
            raise AttributeError(name)

    def createDimension(self, name, size):
        self.dimensions[name] = size

    def createVariable(self, name, dtype, dims, **kw):
        if dtype is str:
            shape = tuple(self.dimensions[d] for d in dims)
            v = MemVar(None, dtype="str")
            object.__setattr__(v, "data", [""] * shape[0])
            self.variables[name] = v
            return v
        shape = tuple(self.dimensions[d] for d in dims)
        np_dtype = {"i2": "int16", "f4": "float32", "f8": "float64"}[dtype]
        v = MemVar(shape, np_dtype)
        self.variables[name] = v
        return v

    def close(self):
        object.__setattr__(self, "closed", True)


# ── Archive Delft3D synthétique ──────────────────────────────
ARCH = TMP / "archive"
(ARCH / "Output" / "Flow").mkdir(parents=True)
(ARCH / "Output" / "wave").mkdir(parents=True)

NN, NM, NLAY_SRC, NTIME = 30, 24, 10, 6
gi, gj = np.meshgrid(np.linspace(0, 1, NM), np.linspace(0, 1, NN))
XX = 700000 + gi * 50000
YY = 6800000 + gj * 60000
LAKE = ((gi - 0.5) / 0.30) ** 2 + ((gj - 0.5) / 0.40) ** 2 <= 1


def make_flow(path, speed, nlay=NLAY_SRC, ntime=NTIME):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", ntime)
    f.createDimension("KMAXOUT_RESTR", nlay)
    f.createDimension("N", NN); f.createDimension("M", NM)
    xv = f.createVariable("XZ", "f8", ("N", "M")); xv[:] = np.where(LAKE, XX, 0)
    yv = f.createVariable("YZ", "f8", ("N", "M")); yv[:] = np.where(LAKE, YY, 0)
    u = f.createVariable("U1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    v = f.createVariable("V1", "f", ("time", "KMAXOUT_RESTR", "N", "M"))
    for t in range(ntime):
        for k in range(nlay):
            u[t, k] = np.where(LAKE, speed * (1 - 0.05 * k), 0).astype("f")
            v[t, k] = np.zeros((NN, NM), "f")
    u.units = "m/s"; u.location = "edge1"
    u.long_name = "U-velocity per layer in U-point (Eulerian)"
    v.units = "m/s"; v.location = "edge2"
    f.close()


def make_wave(path, hs):
    f = netcdf_file(str(path), "w")
    f.createDimension("time", 5)
    f.createDimension("nmax", NN); f.createDimension("mmax", NM)
    xv = f.createVariable("x", "f8", ("nmax", "mmax")); xv[:] = np.where(LAKE, XX, 0)
    yv = f.createVariable("y", "f8", ("nmax", "mmax")); yv[:] = np.where(LAKE, YY, 0)
    for name, unit, amp in [("hsign", "m", hs), ("wlength", "m", 12.0),
                            ("period", "sec", 3.0), ("dir", "deg", 315.0)]:
        vv = f.createVariable(name, "f", ("time", "nmax", "mmax"))
        for t in range(5):
            vv[t] = np.where(LAKE, amp, 0).astype("f")
        vv.units = unit
    f.close()


SPECS = [("wind-sp5.0_wind-dir0.0_wlvl-9.0_sal250.0", 0.20, 0.5, NLAY_SRC),
         ("wind-sp15.0_wind-dir90.0_wlvl-11.0_sal150.0", 0.40, 0.9, NLAY_SRC),
         ("wind-sp25.0_wind-dir180.0_wlvl-13.0_sal50.0", 0.60, 1.3, 4)]
entries = []
for key, spd, hs, nlay in SPECS:
    fp = ARCH / "Output" / "Flow" / f"{key}.nc"
    wp = ARCH / "Output" / "wave" / f"wave_{key}.nc"
    make_flow(fp, spd, nlay=nlay)
    make_wave(wp, hs)
    entries.append({"key": key, "params": {"wind_speed": 5.0, "wind_dir": 0.0,
                                           "wlvl": -9.0, "salinity": 250.0},
                    "files": {"flow": str(fp), "wave": str(wp)}})

index_path = TMP / "scenarios.json"
index_path.write_text(json.dumps({"demo": False, "directory": str(ARCH),
                                  "scenarios": entries}), encoding="utf-8")

compact.INDEX_FILE = index_path
compact.sfield.open_dataset = lambda p: netcdf_file(str(p), "r", mmap=False)
_real_dataset = MemDataset
compact.__dict__["_test_dataset"] = MemDataset

# build() importe netCDF4 localement : on injecte un module factice
fake_nc4 = types.ModuleType("netCDF4")
fake_nc4.Dataset = MemDataset
sys.modules["netCDF4"] = fake_nc4

cfg = {"lake": {"center": {"lon": 137.5, "lat": -28.9}},
       "scenarios": {"rotate_vectors": True, "southern_hemisphere": True}}

MemDataset.instances.clear()
out = compact.build(cfg, [0, 9], -1, out_path=TMP / "out.nc")
ds = MemDataset.instances[-1]

# Le compactage doit REUSSIR pour les trois runs
assert ds.attrs.get("n_failures") is None, \
    f"aucun échec attendu, obtenu {ds.attrs.get('n_failures')}"

# Structure attendue
assert ds.dimensions["scenario"] == 3
assert ds.dimensions["layer"] == 2
for name in ("flow_ue", "flow_vn", "wave_hsign", "wave_wlength",
             "wave_period", "wave_dir", "flow_lon", "flow_lat"):
    assert name in ds.variables, name

# ── Les valeurs relues doivent correspondre à la source ─────
# C'est le contrôle qui manquait : un scale_factor appliqué deux fois
# à l'écriture produisait des courants saturés et des vagues bruitées.
ue_var = ds.variables["flow_ue"]
scale = ue_var.attrs["scale_factor"]
back = np.asarray(ue_var.data[0, 0]).astype("float64") * scale
expected = SPECS[0][1]                      # vitesse imposée du run 0
assert abs(np.abs(back).max() - expected) < 3 * scale, (
    f"relu {np.abs(back).max():.4f} au lieu de {expected:.4f} — "
    "le scale_factor est-il appliqué deux fois ?")

# Les vitesses sont non nulles et croissent avec le scénario
ue = ds.variables["flow_ue"].data
speeds = [np.abs(ue[n, 0]).max() * scale for n in range(3)]
assert speeds[0] > 0.15 and speeds[1] > speeds[0] and speeds[2] > speeds[1], speeds

# La couche 10 est plus lente que la couche 1 (0.05 par couche)
c0 = np.abs(ue[0, 0]).max() * scale
c9 = np.abs(ue[0, 1]).max() * scale
assert c9 < c0, (c0, c9)

# Le run à 4 couches seulement est borné, pas en échec
assert np.abs(ue[2, 1]).max() > 0, "run hétérogène laissé vide"

# Les champs de vagues sont remplis et fidèles
hs = ds.variables["wave_hsign"]
hs_back = np.abs(hs.data[0]).max() * hs.attrs["scale_factor"]
assert abs(hs_back - SPECS[0][2]) < 3 * hs.attrs["scale_factor"], (
    f"hsign relu {hs_back:.4f} au lieu de {SPECS[0][2]:.4f}")

wl = ds.variables["wave_wlength"]
wl_back = np.abs(wl.data[0]).max() * wl.attrs["scale_factor"]
assert abs(wl_back - 12.0) < 3 * wl.attrs["scale_factor"], (
    f"wlength relu {wl_back:.3f} au lieu de 12.0")

# Le nombre de mailles retenues correspond au lac
assert ds.dimensions["flow_cell"] == int(LAKE.sum()), (
    ds.dimensions["flow_cell"], int(LAKE.sum()))

# ── Échec systématique : arrêt plutôt que fichier vide ───────
def broken(*a, **kw):
    raise KeyError("xv")


saved = compact.read_flow
compact.read_flow = broken
try:
    compact.build(cfg, [0], -1, out_path=TMP / "bad.nc")
    raise AssertionError("un échec systématique doit interrompre le "
                         "compactage plutôt que produire un fichier vide")
except compact.SystematicFailure as e:
    assert "échoué" in str(e) or "Aucun scénario" in str(e)
finally:
    compact.read_flow = saved

del sys.modules["netCDF4"]

print("OK — compactage de bout en bout : structure, vitesses, couches, "
      "runs hétérogènes, et arrêt sur échec systématique.")
