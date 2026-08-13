#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lecture d'un champ 2D dans une sortie Delft3D (FLOW ou WAVE).

Points d'attention traites ici :
  - les fichiers FLOW sont volumineux (plusieurs centaines de Mo) :
    seule la tranche demandee est lue, jamais la variable entiere ;
  - les variables portent des dimensions supplementaires (temps,
    couches verticales KMAXOUT_RESTR, constituants LSTSCI) : elles
    sont reduites par selection d'indice ;
  - la grille est decalee (U1 en edge1, V1 en edge2, scalaires en
    face) : si la forme du champ ne correspond pas aux coordonnees
    des centres de mailles, le trace bascule sur les indices de
    grille avec une mention explicite ;
  - les coordonnees sont projetees (metres), pas des degres.

Inspection d'un fichier (a lancer une fois par type de sortie) :
    python pipeline/scenario_field.py --inspect chemin/vers/fichier.nc
"""

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Couples de coordonnees, par ordre de preference.
# Delft3D-FLOW : XZ/YZ = centres de mailles, XCOR/YCOR = coins.
# Delft3D-WAVE : x/y = centres de mailles.
COORD_PAIRS = (("XZ", "YZ"), ("x", "y"), ("longitude", "latitude"),
               ("lon", "lat"), ("XCOR", "YCOR"), ("grid_x", "grid_y"))
COORD_X = tuple(a for a, _ in COORD_PAIRS)
COORD_Y = tuple(b for _, b in COORD_PAIRS)

# Cellules hors domaine : Delft3D y ecrit des sentinelles plutot qu'un
# masque. FLOW utilise 0 et -999.999, WAVE la valeur de remplissage
# NetCDF (~9.97e36). Les conserver etire l'emprise du trace jusqu'a
# l'origine et ecrase le domaine reel dans un coin.
FILL_LIMIT = 1e30
COORD_SENTINELS = (-999.999, -999.0, 999.999)

TIME_DIMS = ("time", "TIME", "t")
# Dimensions verticales (couches) et de constituants : reduites par
# selection d'indice, mais pilotees separement — l'indice de couche et
# l'indice de constituant n'ont rien a voir.
LAYER_DIMS = ("kmaxout_restr", "kmaxout", "kmax", "k", "layer", "nlayers",
              "zlayer", "laydim")
CONSTITUENT_DIMS = ("lstsci", "ltur", "constituent", "nconst")
EXTRA_DIMS = LAYER_DIMS + CONSTITUENT_DIMS

# Libelles de secours quand long_name est absent
# Libelles de secours, utilises quand la variable n'a pas de long_name.
# Ils sont AFFICHES sur le site : en anglais, comme l'interface.
KNOWN_VARS = {
    # Delft3D-FLOW
    "s1": "Water level", "u1": "U velocity", "v1": "V velocity",
    "r1": "Concentration", "rho": "Density",
    "taumax": "Bed shear stress (max)",
    "tauksi": "Bed shear stress U", "taueta": "Bed shear stress V",
    "dps": "Depth",
    # Delft3D-WAVE (SWAN)
    "hsign": "Significant wave height", "hsig": "Significant wave height",
    "hs": "Significant wave height",
    "dir": "Wave direction", "period": "Wave period",
    "wlength": "Wavelength", "wlen": "Wavelength",
    "setup": "Wave set-up", "depth": "Water depth",
}


# Champ propose par defaut, par ordre de pertinence : on ouvre sur la
# grandeur la plus parlante (Hs pour une sortie WAVE, niveau d'eau pour
# une sortie FLOW) plutot que sur la premiere variable rencontree,
# l'ordre des variables dans le fichier n'etant pas garanti.
PRIORITY_NAMES = ("hsign", "hsig", "hs",          # WAVE : hauteur significative
                  "s1",                            # FLOW : niveau d'eau
                  "setup", "taumax", "period", "dir",
                  "wlength", "wlen", "depth", "dps",
                  "u1", "v1", "tauksi", "taueta", "rho", "r1")
PRIORITY_LABELS = ("significant wave height", "water-level", "water level",
                   "set-up", "wave height")


def field_priority(field):
    """Rang de preference (plus petit = propose en premier)."""
    name = field["name"].lower()
    if name in PRIORITY_NAMES:
        rank = PRIORITY_NAMES.index(name)
    else:
        label = (field.get("label") or "").lower()
        hit = next((i for i, p in enumerate(PRIORITY_LABELS) if p in label),
                   None)
        rank = 20 + hit if hit is not None else 99
    return (rank, 0 if field.get("on_coords") else 1)


def _text(value, default=""):
    """Attribut NetCDF -> str (certains fichiers renvoient des bytes)."""
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _pick(names, candidates):
    """Premier nom present (comparaison insensible a la casse)."""
    lower = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _sentinel_mask(v, zero_is_sentinel):
    """Masque des valeurs hors domaine d'un tableau de coordonnees."""
    import numpy as np

    with np.errstate(invalid="ignore"):
        invalid = ~np.isfinite(v)
        invalid |= np.abs(np.nan_to_num(v, nan=0.0)) >= FILL_LIMIT
        for sentinel in COORD_SENTINELS:
            invalid |= np.isclose(v, sentinel)
        if zero_is_sentinel:
            invalid |= (v == 0)
    return invalid


def clean_coords(xv, yv):
    """Remplace par NaN les coordonnees des cellules hors domaine.

    Gere les coordonnees 2D (grille curviligne : une cellule est
    invalide si l'une des deux coordonnees l'est) comme les axes 1D de
    longueurs differentes.

    Retourne (x, y, n_valides, n_total).
    """
    import numpy as np

    xv = np.array(xv, dtype="float64", copy=True)
    yv = np.array(yv, dtype="float64", copy=True)

    # Le zero n'est une sentinelle que pour des coordonnees projetees :
    # en lon/lat, 0 est une valeur legitime (meridien de Greenwich).
    # L'echelle se juge sur le MAXIMUM et non sur la mediane : quand la
    # plupart des cellules sont hors domaine, la mediane vaut 0 et la
    # regle s'effondrerait. Une seule cellule a 6,8e6 suffit a etablir
    # que les coordonnees sont en metres (un degre ne depasse pas 360).
    def _scale(v):
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(v) & (np.abs(np.nan_to_num(v, nan=0.0)) < FILL_LIMIT)
            for sentinel in COORD_SENTINELS:
                ok &= ~np.isclose(v, sentinel)
        return float(np.abs(v[ok]).max()) if ok.any() else 0.0

    zero_is_sentinel = max(_scale(xv), _scale(yv)) > 1000

    ix = _sentinel_mask(xv, zero_is_sentinel)
    iy = _sentinel_mask(yv, zero_is_sentinel)

    if xv.shape == yv.shape:
        invalid = ix | iy
        xv[invalid] = np.nan
        yv[invalid] = np.nan
        return xv, yv, int((~invalid).sum()), int(invalid.size)

    # Axes 1D independants
    xv[ix] = np.nan
    yv[iy] = np.nan
    n_valid = int((~ix).sum()) * int((~iy).sum())
    return xv, yv, n_valid, int(xv.size) * int(yv.size)


def read_coords(ds, names, z_shape=None, min_fraction=0.01):
    """Premier couple de coordonnees exploitable.

    Un couple est retenu s'il existe, a la bonne forme, et conserve
    assez de cellules valides apres nettoyage — de quoi basculer sur
    XCOR/YCOR si XZ/YZ sont vides.
    """
    lower = {n.lower(): n for n in names}
    for xa, ya in COORD_PAIRS:
        xn, yn = lower.get(xa.lower()), lower.get(ya.lower())
        if not xn or not yn:
            continue
        xv, yv, n_valid, n_total = clean_coords(ds.variables[xn][:],
                                                ds.variables[yn][:])
        if z_shape is not None and xv.ndim == 2 and xv.shape != z_shape:
            continue
        if n_total and n_valid / n_total < min_fraction:
            continue
        # Grille degeneree (coordonnees toutes identiques, souvent
        # remplies de zeros) : aucune information spatiale exploitable.
        import numpy as np
        with np.errstate(invalid="ignore"):
            spread = max(np.nanmax(xv) - np.nanmin(xv),
                         np.nanmax(yv) - np.nanmin(yv)) if n_valid else 0.0
        if not np.isfinite(spread) or spread <= 0:
            continue
        return xn, yn, xv, yv, n_valid, n_total
    return None, None, None, None, 0, 0


def open_dataset(path):
    """Ouvre le NetCDF (import paresseux de netCDF4)."""
    try:
        from netCDF4 import Dataset
    except ImportError:
        raise RuntimeError(
            "netCDF4 is not installed (pip install netCDF4) — required "
            "to read Delft3D output.")

    name = Path(path).name
    if name.startswith("._"):
        raise ValueError(
            f"'{name}' is a macOS metadata file (AppleDouble), not a "
            "Delft3D output. Re-run pipeline/scenario_index.py: these files "
            "are now skipped.")
    return Dataset(path, "r")


def is_time_dim(dim):
    return dim.lower() in [d.lower() for d in TIME_DIMS]


def _matches(dim, names):
    d = dim.lower()
    return any(d == n or d.startswith(n) for n in names)


def is_layer_dim(dim):
    return _matches(dim, LAYER_DIMS)


def is_constituent_dim(dim):
    return _matches(dim, CONSTITUENT_DIMS)


def is_extra_dim(dim):
    return _matches(dim, EXTRA_DIMS)


def dim_kind(dim):
    if is_time_dim(dim):
        return "time"
    if is_layer_dim(dim):
        return "layer"
    if is_constituent_dim(dim):
        return "constituent"
    return "other"


def describe_dataset(ds):
    """Inventaire : coordonnees detectees et champs affichables."""
    names = list(ds.variables)
    xname, yname, _, _, n_valid, n_total = read_coords(ds, names)
    coord_shape = None
    if xname is not None:
        coord_shape = tuple(int(s) for s in ds.variables[xname].shape)

    # Toutes les variables de coordonnees, pas seulement celles retenues :
    # XCOR/YCOR (coins de mailles) ne sont pas des champs physiques.
    coord_names = {c.lower() for c in COORD_X + COORD_Y}

    fields = []
    for name, var in ds.variables.items():
        if name in (xname, yname) or name.lower() in coord_names:
            continue
        label_probe = (_text(getattr(var, "long_name", "")) + " "
                       + _text(getattr(var, "standard_name", ""))).lower()
        if "coordinate of" in label_probe or "coordinates of" in label_probe:
            continue
        spatial = [d for d in var.dimensions
                   if not is_time_dim(d) and not is_extra_dim(d)]
        if len(spatial) < 2:
            continue
        shape = tuple(int(s) for s in var.shape)
        fields.append({
            "name": name,
            "label": (_text(getattr(var, "long_name", None))
                      or KNOWN_VARS.get(name.lower()) or name),
            "units": _text(getattr(var, "units", "")),
            "location": _text(getattr(var, "location", "")),
            "dims": list(var.dimensions),
            "shape": list(shape),
            "extra_dims": [d for d in var.dimensions if is_extra_dim(d)],
            "has_time": any(is_time_dim(d) for d in var.dimensions),
            "on_coords": coord_shape is not None and shape[-2:] == coord_shape[-2:],
        })
    return {"x": xname, "y": yname, "coord_shape": coord_shape,
            "n_valid_cells": n_valid, "n_cells": n_total,
            "fields": fields}


def build_slice(var, time_index=-1, layer_index=0, constituent_index=0):
    """Tranche a lire : dimensions non spatiales reduites par indice,
    les deux dernieres (spatiales) conservees.

    Retourne (tuple d'indices, notes lisibles, description des axes
    reduits pour l'interface).
    """
    idx, notes, axes = [], [], []
    ndim = len(var.dimensions)
    for i, dim in enumerate(var.dimensions):
        size = int(var.shape[i])
        if i >= ndim - 2:                    # dimensions spatiales
            idx.append(slice(None))
            continue

        kind = dim_kind(dim)
        if kind == "time":
            k = time_index
        elif kind == "layer":
            k = layer_index
        elif kind == "constituent":
            k = constituent_index
        else:
            k = 0
        # Bornage complet : certains runs ont moins de couches ou de pas
        # de temps que les autres, voire une dimension vide (simulation
        # interrompue avant la premiere ecriture).
        if size <= 0:
            raise ValueError(
                f"dimension '{dim}' is empty — truncated output")
        if k < 0:
            k = max(k, -size)
        else:
            k = min(k, size - 1)

        idx.append(k)
        axes.append({"dim": dim, "kind": kind, "size": size,
                     "index": (size - 1 if k == -1 else k)})
        if size > 1:
            shown = "dernier" if k == -1 else k
            notes.append(f"{dim}={shown} sur {size}")
    return tuple(idx), notes, axes


ZERO_MASK_DEFAULT = ("u1", "v1", "tauksi", "taueta", "taumax")


def should_mask_zero(varname, setting):
    """Faut-il ecarter les valeurs exactement nulles ?

    Dans les cellules seches ou hors domaine, Delft3D ecrit 0 plutot
    qu'une valeur manquante : conserve, ce zero ecrase la dynamique du
    champ de vitesse. setting vaut True, False ou "auto" (defaut :
    seulement les champs vectoriels et de contrainte).
    """
    if setting is True:
        return True
    if setting is False:
        return False
    return varname.lower() in ZERO_MASK_DEFAULT


def read_field(path, varname=None, max_points=180, time_index=-1,
               layer_index=0, constituent_index=0, mask_zero="auto"):
    """Lit un champ 2D et le renvoie sur une grille reguliere.

    Retourne {x, y, z, var, label, units, regridded, ...}.
    """
    import numpy as np

    ds = open_dataset(path)
    try:
        info = describe_dataset(ds)
        if not info["fields"]:
            raise ValueError("No 2-D field found in this file.")

        if varname is None:
            varname = min(info["fields"], key=field_priority)["name"]
        if varname not in ds.variables:
            raise ValueError(f"Variable '{varname}' not found in this file.")

        var = ds.variables[varname]
        sl, notes, axes = build_slice(var, time_index, layer_index,
                                      constituent_index)
        z = np.ma.masked_invalid(np.ma.masked_array(var[sl]).astype("float64"))
        if should_mask_zero(varname, mask_zero):
            z = np.ma.masked_where(z == 0, z)
        if z.ndim != 2:
            raise ValueError(
                f"'{varname}' is still {z.ndim}-D after reduction "
                f"(dims {var.dimensions}).")

        meta = {
            "var": varname,
            "label": (_text(getattr(var, "long_name", None))
                      or KNOWN_VARS.get(varname.lower()) or varname),
            "units": _text(getattr(var, "units", "")),
            "location": _text(getattr(var, "location", "")),
            "reduction": notes,
            "axes": axes,
        }

        names = list(ds.variables)
        xname, yname, xv, yv, n_valid, n_total = read_coords(
            ds, names, z_shape=z.shape)
        if xname is None:
            # Distinguer "pas de coordonnees" de "grille decalee" : les
            # variables aux faces (U1, V1) peuvent avoir une forme
            # differente de celle des centres de mailles.
            alt, _, alt_xv, _, _, _ = read_coords(ds, names)
            if alt is not None and getattr(alt_xv, "ndim", 0) == 2:
                meta["note"] = (f"field {tuple(z.shape)} staggered relative "
                                f"to coordinates {tuple(alt_xv.shape)}")
            return _payload(np.arange(z.shape[1]), np.arange(z.shape[0]), z,
                            meta, regridded=False, on_index=True)
        meta["coords"] = f"{xname}/{yname}"
        meta["n_valid_cells"] = n_valid
        meta["n_cells"] = n_total

        if xv.ndim == 1 and yv.ndim == 1:
            return _thin_rectilinear(xv, yv, z, max_points, meta)

        # Grille reguliere ecrite sous forme de tableaux 2D : les axes
        # se deduisent directement, ce qui evite une triangulation de
        # plusieurs dizaines de milliers de points et conserve la
        # resolution native.
        axes = rectilinear_axes(xv, yv)
        if axes is not None:
            return _thin_rectilinear(axes[0], axes[1], z, max_points, meta)
        return _regrid_curvilinear(xv, yv, z, max_points, meta)
    finally:
        ds.close()


def rectilinear_axes(xv, yv, rtol=1e-6):
    """Si les coordonnees 2D decrivent une grille reguliere, renvoie
    (axe_x, axe_y) ; sinon None (grille reellement curviligne)."""
    import numpy as np

    if xv.ndim != 2 or yv.ndim != 2 or xv.shape != yv.shape:
        return None
    if not (np.isfinite(xv).all() and np.isfinite(yv).all()):
        return None  # cellules inactives : on repasse par l'interpolation

    x_axis, y_axis = xv[0, :], yv[:, 0]
    span = max(np.ptp(x_axis), np.ptp(y_axis)) or 1.0
    tol = span * rtol
    if (np.abs(xv - x_axis).max() <= tol
            and np.abs(yv - y_axis[:, None]).max() <= tol):
        return x_axis, y_axis
    return None


def _thin_rectilinear(xv, yv, z, max_points, meta):
    """Grille reguliere : sous-echantillonnage simple si trop dense."""
    if z.shape == (yv.size, xv.size):
        pass
    elif z.shape == (xv.size, yv.size):
        z = z.T
    else:
        import numpy as np
        return _payload(np.arange(z.shape[1]), np.arange(z.shape[0]), z,
                        meta, regridded=False, on_index=True)

    sy = max(1, z.shape[0] // max_points)
    sx = max(1, z.shape[1] // max_points)
    return _payload(xv[::sx], yv[::sy], z[::sy, ::sx], meta, regridded=False)


def _regrid_curvilinear(xv, yv, z, max_points, meta):
    """Grille curviligne : interpolation sur une grille reguliere."""
    import numpy as np
    from scipy.interpolate import griddata

    if xv.shape != z.shape or yv.shape != z.shape:
        raise ValueError(f"2-D coordinates {xv.shape} do not match the "
                         f"field {z.shape}.")

    zf = np.ma.filled(z, np.nan)
    good = np.isfinite(zf) & np.isfinite(xv) & np.isfinite(yv)
    if not good.any():
        raise ValueError("Field is entirely masked.")

    pts = np.column_stack([xv[good].ravel(), yv[good].ravel()])
    vals = zf[good].ravel()

    nx = ny = int(max_points)
    gx = np.linspace(pts[:, 0].min(), pts[:, 0].max(), nx)
    gy = np.linspace(pts[:, 1].min(), pts[:, 1].max(), ny)
    gz = griddata(pts, vals, tuple(np.meshgrid(gx, gy)), method="linear")

    return _payload(gx, gy, np.ma.masked_invalid(gz), meta, regridded=True)


def _payload(xv, yv, z, meta, regridded, on_index=False):
    import numpy as np

    zf = np.ma.filled(np.ma.masked_invalid(z), np.nan)
    rows = [[None if not np.isfinite(v) else round(float(v), 4) for v in row]
            for row in zf]
    finite = zf[np.isfinite(zf)]
    out = {
        "x": [round(float(v), 3) for v in xv],
        "y": [round(float(v), 3) for v in yv],
        "z": rows,
        "n_x": len(xv), "n_y": len(yv),
        "regridded": regridded,
        "on_index": on_index,
        "zmin": round(float(finite.min()), 4) if finite.size else None,
        "zmax": round(float(finite.max()), 4) if finite.size else None,
    }
    out.update(meta)
    return out


def grid_rotation(xv, yv):
    """Angle local des axes de la grille curviligne, en radians.

    Delft3D exprime U1 et V1 dans le repere de la grille (ksi, eta) et
    non selon x/y : sur une grille tournee, tracer les composantes
    brutes oriente les fleches de travers. L'angle est estime par le
    gradient des coordonnees le long du dernier axe (ksi).
    """
    import numpy as np

    if xv.ndim != 2:
        return None
    dx = np.gradient(xv, axis=1)
    dy = np.gradient(yv, axis=1)
    with np.errstate(invalid="ignore"):
        ang = np.arctan2(dy, dx)
    return ang


def _smooth_nan(grid, sigma):
    """Lissage gaussien insensible aux NaN (moyenne ponderee).

    Reprend la methode du lecteur de reference : les NaN sont mis a 0
    dans le numerateur comme dans le poids, puis le resultat est
    renormalise et les bords du domaine restaures.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter

    if not sigma:
        return grid
    nan_mask = np.isnan(grid)
    filled = np.where(nan_mask, 0.0, grid)
    weights = np.where(nan_mask, 0.0, 1.0)
    num = gaussian_filter(filled, sigma=sigma)
    den = gaussian_filter(weights, sigma=sigma)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    out[nan_mask] = np.nan          # preserver les bords du domaine
    return out


def read_currents(path, u_name="U1", v_name="V1", n_arrows=30, grid_res=250,
                  smooth=2.0, time_index=-1, layer_index=0, rotate=True,
                  vmin=None, vmax=None, bounds=None, max_points=None):
    """Carte de courants : champ d'intensite + fleches.

    Suit la methode du lecteur de reference (map_data_quiver) :
      - masque des coordonnees hors domaine ;
      - intensite interpolee lineairement sur une grille fine, valeurs
        sous 1e-6 mises a NaN (transparentes) ;
      - lissage gaussien optionnel, insensible aux NaN ;
      - fleches sur une grille plus grossiere, composantes interpolees
        au plus proche voisin, intensite en lineaire, et rejet des
        vitesses exactement nulles.

    Retourne {speed: {x, y, z}, arrows: {x, y, u, v, speed}, ...}.
    """
    import numpy as np
    from scipy.interpolate import griddata

    if max_points:
        grid_res = min(int(grid_res), int(max_points))

    ds = open_dataset(path)
    try:
        names = list(ds.variables)
        lower = {m.lower(): m for m in names}
        u_name = lower.get(u_name.lower())
        v_name = lower.get(v_name.lower())
        if not u_name or not v_name:
            raise ValueError("Velocity components not found in this file.")

        uvar, vvar = ds.variables[u_name], ds.variables[v_name]
        su, _, axes = build_slice(uvar, time_index, layer_index)
        sv, _, _ = build_slice(vvar, time_index, layer_index)
        u = np.ma.filled(np.ma.masked_invalid(
            np.ma.masked_array(uvar[su]).astype("float64")), np.nan)
        v = np.ma.filled(np.ma.masked_invalid(
            np.ma.masked_array(vvar[sv]).astype("float64")), np.nan)
        if u.ndim != 2 or u.shape != v.shape:
            raise ValueError("Velocity components have unexpected shapes.")

        xname, yname, xv, yv, n_valid, n_total = read_coords(
            ds, names, z_shape=u.shape)
        if xname is None:
            raise ValueError("Coordinates incompatible with the velocity "
                             "field.")

        rotated = False
        if rotate:
            ang = grid_rotation(xv, yv)
            if ang is not None and np.isfinite(ang).any():
                ca, sa = np.cos(ang), np.sin(ang)
                u, v = u * ca - v * sa, u * sa + v * ca
                rotated = True

        speed = np.sqrt(u ** 2 + v ** 2)

        # Le jeu de points d'interpolation retient TOUTES les mailles du
        # domaine, y compris les seches ou la vitesse est nulle. Ce sont
        # elles qui tirent le champ interpole vers zero au bord du lac ;
        # le seuil applique ensuite les rend transparentes et fait
        # apparaitre le trait de cote. Les ecarter avant interpolation
        # remplirait l'enveloppe convexe du domaine (le lac disparait
        # sous un aplat triangule).
        good = np.isfinite(xv) & np.isfinite(yv) & np.isfinite(speed)
        if not good.any():
            raise ValueError("No valid cells in this scenario.")
        if not (speed[good] > 0).any():
            raise ValueError("No non-zero currents in this scenario.")

        pts = np.column_stack([xv[good].ravel(), yv[good].ravel()])
        su_v, sv_v = u[good].ravel(), v[good].ravel()
        spd_v = speed[good].ravel()

        x0, x1 = pts[:, 0].min(), pts[:, 0].max()
        y0, y1 = pts[:, 1].min(), pts[:, 1].max()
        if bounds:                       # emprise imposee (xmin, xmax, ymin, ymax)
            bx0, bx1, by0, by1 = bounds
            x0, x1 = max(x0, bx0), min(x1, bx1)
            y0, y1 = max(y0, by0), min(y1, by1)
            if not (x1 > x0 and y1 > y0):
                raise ValueError("Requested bounds do not intersect the model "
                                 "domain.")

        # ── Champ d'intensite (fond) ─────────────────────────
        gx = np.linspace(x0, x1, int(grid_res))
        gy = np.linspace(y0, y1, int(grid_res))
        gxx, gyy = np.meshgrid(gx, gy)
        gspd = griddata(pts, spd_v, (gxx, gyy), method="linear")
        gspd[gspd < 1e-6] = np.nan          # cellules seches -> transparent
        gspd = _smooth_nan(gspd, smooth)

        rows = [[None if not np.isfinite(val) else round(float(val), 5)
                 for val in row] for row in gspd]
        finite = gspd[np.isfinite(gspd)]

        # ── Fleches (grille plus grossiere) ──────────────────
        ax_ = np.linspace(x0, x1, int(n_arrows))
        ay_ = np.linspace(y0, y1, int(n_arrows))
        axx, ayy = np.meshgrid(ax_, ay_)
        au = griddata(pts, su_v, (axx, ayy), method="nearest")
        av = griddata(pts, sv_v, (axx, ayy), method="nearest")
        asp = griddata(pts, spd_v, (axx, ayy), method="linear")
        # Une fleche n'est tracee que la ou la vitesse est non nulle :
        # le plus proche voisin ramene 0 sur les mailles seches.
        keep = (np.isfinite(asp) & np.isfinite(au) & np.isfinite(av)
                & (np.sqrt(au ** 2 + av ** 2) > 0))

        arrows = {"x": [], "y": [], "u": [], "v": [], "speed": []}
        for iy in range(ay_.size):
            for ix in range(ax_.size):
                if not keep[iy, ix]:
                    continue
                arrows["x"].append(round(float(ax_[ix]), 2))
                arrows["y"].append(round(float(ay_[iy]), 2))
                arrows["u"].append(round(float(au[iy, ix]), 5))
                arrows["v"].append(round(float(av[iy, ix]), 5))
                arrows["speed"].append(round(float(asp[iy, ix]), 5))

        return {
            "speed": {"x": [round(float(t), 2) for t in gx],
                      "y": [round(float(t), 2) for t in gy],
                      "z": rows},
            "arrows": arrows,
            "u_var": u_name, "v_var": v_name,
            "units": _text(getattr(uvar, "units", "m/s")),
            "label": "Current speed",
            "rotated": rotated,
            "smooth": float(smooth or 0.0),
            "n_arrows": len(arrows["x"]),
            "n_x": len(gx), "n_y": len(gy),
            "zmin": round(float(finite.min()), 5) if finite.size else None,
            "zmax": round(float(finite.max()), 5) if finite.size else None,
            "vmin": vmin, "vmax": vmax,
            "axes": axes,
            "coords": f"{xname}/{yname}",
            "n_valid_cells": n_valid, "n_cells": n_total,
        }
    finally:
        ds.close()


def main():
    parser = argparse.ArgumentParser(description="Lecture d'un champ Delft3D")
    parser.add_argument("--inspect", metavar="FICHIER",
                        help="Liste les variables et coordonnées détectées")
    args = parser.parse_args()

    if not args.inspect:
        parser.error("préciser --inspect FICHIER")

    ds = open_dataset(args.inspect)
    try:
        info = describe_dataset(ds)
        print(f"Fichier : {args.inspect}")
        print(f"  Coordonnées détectées : x={info['x']}  y={info['y']}"
              f"  {info['coord_shape'] or ''}")
        if info.get("n_cells"):
            pct = 100.0 * info["n_valid_cells"] / info["n_cells"]
            print(f"  Cellules dans le domaine : {info['n_valid_cells']} / "
                  f"{info['n_cells']} ({pct:.0f} %) — les autres portent "
                  "une sentinelle (0, -999.999 ou remplissage)")
        print("  Dimensions : "
              + ", ".join(f"{k}={len(v)}" for k, v in ds.dimensions.items()))
        print(f"\n  Champs affichables ({len(info['fields'])}) :")
        print(f"    {'nom':<12} {'libellé':<34} {'unité':<8} "
              f"{'forme':<20} {'lieu':<7} grille")
        for f in info["fields"]:
            print(f"    {f['name']:<12} {f['label'][:33]:<34} "
                  f"{f['units'][:7]:<8} {str(tuple(f['shape'])):<20} "
                  f"{f['location'][:6]:<7} "
                  f"{'centres' if f['on_coords'] else 'décalée'}")
            if f["extra_dims"]:
                det = ", ".join(f"{d} ({dim_kind(d)})" for d in f["extra_dims"])
                print(f"      dimensions réduites : {det}")
        print("\n  À reporter dans config.yaml -> scenarios.variables "
              "(champs à proposer sur le site).")
    finally:
        ds.close()


if __name__ == "__main__":
    main()


# ══════════════════════════════════════════════════════════════
# Couches cartographiques : champ scalaire + fleches, echantillonnes
# sur une grille geographique reguliere pour un affichage direct sur
# la carte (Leaflet attend du WGS84, le modele est en metres projetes).
# ══════════════════════════════════════════════════════════════

MAP_LAYERS = {
    "currents": {"source": "flow", "mode": "vector",
                 "u": "U1", "v": "V1",
                 "label": "Current speed", "units": "m/s",
                 "vmin": 0.0, "vmax": 0.5},
    "hsign": {"source": "wave", "mode": "scalar", "var": "hsign",
              "dir": "dir", "label": "Wave height", "units": "m",
              "vmin": 0.0, "vmax": None},
    "wlength": {"source": "wave", "mode": "scalar", "var": "wlength",
                "dir": "dir", "label": "Wavelength", "units": "m",
                "vmin": 0.0, "vmax": None},
    "period": {"source": "wave", "mode": "scalar", "var": "period",
               "dir": "dir", "label": "Wave period", "units": "s",
               "vmin": 0.0, "vmax": None},
}


def wet_mask(ds, varname, time_index, layer_index=0):
    """Masque des mailles en eau, ou None si indisponible.

    Une maille seche porte zero (ou une valeur manquante) dans le
    niveau d'eau cote FLOW comme dans la profondeur cote WAVE. C'est
    le seul critere fiable : la grandeur affichee, elle, peut
    legitimement valoir zero en eau calme.
    """
    import numpy as np

    try:
        arr, _, _, _ = _read_2d(ds, varname, time_index, layer_index)
    except ValueError:
        return None
    return np.isfinite(arr) & (np.abs(arr) > 0)


def _read_2d(ds, name, time_index, layer_index, constituent_index=0):
    """Variable reduite a deux dimensions spatiales."""
    import numpy as np

    lower = {m.lower(): m for m in ds.variables}
    real = lower.get(name.lower())
    if not real:
        raise ValueError(f"Variable '{name}' not found in this output.")
    var = ds.variables[real]
    sl, notes, axes = build_slice(var, time_index, layer_index,
                                  constituent_index)
    arr = np.ma.filled(np.ma.masked_invalid(
        np.ma.masked_array(var[sl]).astype("float64")), np.nan)
    if arr.ndim != 2:
        raise ValueError(f"'{real}' is not a 2-D field after reduction.")
    return arr, real, notes, axes


def assemble_map(plon, plat, values, spec, extra=None, grid_res=260,
                 n_arrows=26, smooth=2.0, vmin=None, vmax=None,
                 wave_dir_convention="from", wet=None):
    """Assemble un raster lon/lat regulier et un jeu de fleches.

    Partage par les deux sources : lecture directe des NetCDF Delft3D
    et lecture du fichier compact. Les points d'entree sont deja en
    degres et les composantes de vitesse deja orientees est/nord.
    """
    import numpy as np
    from scipy.interpolate import griddata

    extra = extra or {}
    finite_pts = np.isfinite(plon) & np.isfinite(plat) & np.isfinite(values)
    if not finite_pts.any():
        raise ValueError("No valid cells in this output.")
    plon, plat = plon[finite_pts], plat[finite_pts]
    values = np.where(np.isfinite(values), values, 0.0)[finite_pts]

    # Masque du domaine en eau. Sans masque explicite, on retombe sur
    # « valeur non nulle », ce qui confond un lac CALME (courants nuls
    # mais en eau) avec un lac SEC. Des que la source permet de les
    # distinguer — niveau d'eau cote FLOW, profondeur cote WAVE — le
    # masque est fourni et cette ambiguite disparait.
    if wet is None:
        wet_pts = values > 0
    else:
        wet_pts = np.asarray(wet, dtype=bool)[finite_pts]
    if not wet_pts.any():
        raise ValueError("No wet cells in this scenario.")

    lon0, lon1 = float(plon.min()), float(plon.max())
    lat0, lat1 = float(plat.min()), float(plat.max())

    # Un degre de longitude est plus court qu'un degre de latitude :
    # sans cette mise a l'echelle, la triangulation de l'interpolation
    # serait etiree dans une direction.
    kx = math.cos(math.radians((lat0 + lat1) / 2)) or 1.0
    src = np.column_stack([plon * kx, plat])

    glon = np.linspace(lon0, lon1, int(grid_res))
    glat = np.linspace(lat0, lat1, int(grid_res))
    mlon, mlat = np.meshgrid(glon, glat)
    tgt = (mlon * kx, mlat)

    grid = griddata(src, values, tgt, method="linear")
    # Le plus proche voisin sert de porte : un point n'est colore que si
    # la maille du modele la plus proche est en eau. Le champ lui-meme
    # peut valoir zero (lac calme) sans disparaitre pour autant.
    near_wet = griddata(src, wet_pts.astype("float64"), tgt,
                        method="nearest")
    grid[near_wet < 0.5] = np.nan
    grid = _smooth_nan(grid, smooth)

    finite = grid[np.isfinite(grid)]
    rows = [[None if not np.isfinite(t) else round(float(t), 4)
             for t in row] for row in grid]

    alon = np.linspace(lon0, lon1, int(n_arrows))
    alat = np.linspace(lat0, lat1, int(n_arrows))
    mal, mab = np.meshgrid(alon, alat)
    atgt = (mal * kx, mab)
    amag = griddata(src, values, atgt, method="linear")
    awet = griddata(src, wet_pts.astype("float64"), atgt,
                    method="nearest") >= 0.5

    if spec["mode"] == "vector" and "ue" in extra:
        ue = griddata(src, np.asarray(extra["ue"])[finite_pts], atgt,
                      method="nearest")
        vn = griddata(src, np.asarray(extra["vn"])[finite_pts], atgt,
                      method="nearest")
        # np.isfinite(amag) est indispensable : l'intensite vient d'une
        # interpolation LINEAIRE (NaN hors de l'enveloppe convexe) alors
        # que le masque vient du plus proche voisin (defini partout).
        # Sans cette garde, une fleche peut porter une valeur NaN, que
        # le navigateur refuse ensuite comme JSON invalide.
        keep = (awet & np.isfinite(amag) & np.isfinite(ue) & np.isfinite(vn)
                & (np.hypot(ue, vn) > 0))
        bearing = np.degrees(np.arctan2(ue, vn))
    elif "dir" in extra:
        adir = griddata(src, np.asarray(extra["dir"])[finite_pts], atgt,
                        method="nearest")
        keep = awet & np.isfinite(adir) & np.isfinite(amag)
        bearing = adir + (180.0 if wave_dir_convention == "from" else 0.0)
    else:
        keep = np.zeros_like(amag, dtype=bool)
        bearing = np.zeros_like(amag)

    arrows = {"lat": [], "lon": [], "bearing": [], "value": []}
    for iy in range(alat.size):
        for ix in range(alon.size):
            if not keep[iy, ix]:
                continue
            quad = (mab[iy, ix], mal[iy, ix], bearing[iy, ix], amag[iy, ix])
            if not all(np.isfinite(t) for t in quad):
                continue        # jamais de non-fini dans la charge utile
            arrows["lat"].append(round(float(quad[0]), 6))
            arrows["lon"].append(round(float(quad[1]), 6))
            arrows["bearing"].append(round(float(quad[2]) % 360.0, 2))
            arrows["value"].append(round(float(quad[3]), 5))

    dlat = (glat[-1] - glat[0]) / max(1, len(glat) - 1)
    dlon = (glon[-1] - glon[0]) / max(1, len(glon) - 1)
    lo = spec["vmin"] if vmin is None else vmin
    hi = spec["vmax"] if vmax is None else vmax

    return {
        "label": spec["label"], "units": spec["units"],
        # bounds : cadre de l'IMAGE, etendu d'une demi-maille pour que
        # le raster se cale sur ses bords.
        # extent : emprise des POINTS d'echantillonnage, sur laquelle
        # les fleches sont placees. Confondre les deux decale les
        # fleches d'une demi-maille (~200 m ici).
        "bounds": [[round(glat[0] - dlat / 2, 6), round(glon[0] - dlon / 2, 6)],
                   [round(glat[-1] + dlat / 2, 6),
                    round(glon[-1] + dlon / 2, 6)]],
        "extent": [[round(float(glat[0]), 6), round(float(glon[0]), 6)],
                   [round(float(glat[-1]), 6), round(float(glon[-1]), 6)]],
        "lat": [round(float(t), 6) for t in glat],
        "lon": [round(float(t), 6) for t in glon],
        "z": rows, "n_x": len(glon), "n_y": len(glat),
        "arrows": arrows, "n_arrows": len(arrows["lat"]),
        "arrow_scaled": spec["mode"] == "vector",
        "zmin": round(float(finite.min()), 4) if finite.size else None,
        "zmax": round(float(finite.max()), 4) if finite.size else None,
        "vmin": lo, "vmax": hi,
        "smooth": float(smooth or 0.0),
        "n_wet": int(wet_pts.sum()),
        "masked": wet is not None,
    }


def read_map_layer(path, layer="currents", zone=53, south=True,
                   grid_res=260, n_arrows=26, smooth=2.0,
                   time_index=-1, layer_index=0, rotate=True,
                   vmin=None, vmax=None, wave_dir_convention="from"):
    """Couche prete a superposer sur une carte.

    Retourne un raster sur grille lon/lat reguliere (donc directement
    affichable par-dessus la carte) et un jeu de fleches decrites par
    leur position et leur azimut vrai.

    Les mailles seches restent dans le jeu d'interpolation avec une
    valeur nulle : ce sont elles qui dessinent le trait de cote une
    fois le seuil applique.
    """
    import numpy as np
    from scipy.interpolate import griddata

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import geo

    spec = MAP_LAYERS.get(layer)
    if spec is None:
        raise ValueError(f"Unknown map layer '{layer}'.")

    ds = open_dataset(path)
    try:
        if spec["mode"] == "vector":
            u, u_name, notes, axes = _read_2d(ds, spec["u"], time_index,
                                              layer_index)
            v, _, _, _ = _read_2d(ds, spec["v"], time_index, layer_index)
            value = np.sqrt(u ** 2 + v ** 2)
            # Le niveau d'eau distingue les mailles en eau des mailles
            # seches, meme quand la vitesse y est nulle.
            wet2d = wet_mask(ds, "S1", time_index)
        else:
            value, u_name, notes, axes = _read_2d(ds, spec["var"], time_index,
                                                  layer_index)
            try:
                wdir, _, _, _ = _read_2d(ds, spec["dir"], time_index,
                                         layer_index)
            except ValueError:
                wdir = None
            wet2d = wet_mask(ds, "depth", time_index)
            u = v = None

        xname, yname, xv, yv, n_valid, n_total = read_coords(
            ds, list(ds.variables), z_shape=value.shape)
        if xname is None:
            raise ValueError("Coordinates incompatible with this field.")

        if spec["mode"] == "vector" and rotate:
            ang = grid_rotation(xv, yv)
            if ang is not None and np.isfinite(ang).any():
                ca, sa = np.cos(ang), np.sin(ang)
                u, v = u * ca - v * sa, u * sa + v * ca

        # Toutes les mailles dont les COORDONNEES sont valides entrent
        # dans l'interpolation, y compris les seches. Selon la sortie,
        # une maille seche porte 0 (FLOW) ou une valeur manquante
        # (WAVE) : les deux sont ramenees a 0 pour que le champ
        # interpole retombe a zero au bord du lac et soit ensuite rendu
        # transparent. Sans cela, seules les mailles en eau
        # subsisteraient et l'interpolation lineaire remplirait
        # l'enveloppe convexe du domaine — des valeurs apparaitraient
        # alors sur la terre ferme.
        good = np.isfinite(xv) & np.isfinite(yv)
        if not good.any():
            raise ValueError("No valid cells in this output.")
        value = np.where(np.isfinite(value), value, 0.0)
        pts = np.column_stack([xv[good].ravel(), yv[good].ravel()])
        vals = value[good].ravel()

        # Coordonnees geographiques des mailles du modele
        plon, plat = [], []
        for cx, cy in pts:
            lo, la = geo.utm_to_lonlat(cx, cy, zone, south)
            plon.append(lo); plat.append(la)
        plon = np.asarray(plon); plat = np.asarray(plat)

        if spec["mode"] == "vector":
            # ksi/eta -> x/y (deja fait) -> est/nord (convergence)
            gamma = np.radians([geo.grid_convergence(lo, la, zone)
                                for lo, la in zip(plon, plat)])
            ue = u[good].ravel() * np.cos(gamma) - v[good].ravel() * np.sin(gamma)
            vn = u[good].ravel() * np.sin(gamma) + v[good].ravel() * np.cos(gamma)
            extra = {"ue": ue, "vn": vn}
        elif wdir is not None:
            wd = np.where(np.isfinite(wdir), wdir, 0.0)
            extra = {"dir": wd[good].ravel()}
        else:
            extra = {}

        wet = None if wet2d is None else wet2d[good].ravel()
        out = assemble_map(plon, plat, vals, spec, extra=extra,
                           grid_res=grid_res, n_arrows=n_arrows,
                           smooth=smooth, vmin=vmin, vmax=vmax,
                           wave_dir_convention=wave_dir_convention,
                           wet=wet)
        out.update({
            "layer": layer, "var": u_name, "zone": zone,
            "reduction": notes, "axes": axes,
            "coords": f"{xname}/{yname}",
            "n_valid_cells": n_valid, "n_cells": n_total,
        })
        return out
    finally:
        ds.close()
