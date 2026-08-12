#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lecture du fichier compact produit par pipeline/compact.py.

Le fichier est ouvert une seule fois et garde en memoire les
coordonnees ainsi que la table des scenarios : servir une couche
revient alors a lire une tranche de quelques dizaines de kilo-octets,
au lieu d'ouvrir un NetCDF de 250 Mo. C'est ce qui rend le parcours de
la frise temporelle instantane.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import scenario_field as sfield  # noqa: E402

FILL = -32768


def open_dataset(path):
    """Ouverture du fichier compact (isolee pour permettre les tests)."""
    from netCDF4 import Dataset

    ds = Dataset(str(path), "r")
    if hasattr(ds, "set_auto_maskandscale"):
        # Le facteur d'echelle est applique ici, pour un comportement
        # identique quelle que soit la bibliotheque de lecture.
        ds.set_auto_maskandscale(False)
    return ds


class CompactStore:
    """Acces en lecture au fichier compact."""

    def __init__(self, path, opener=None):
        self.path = Path(path)
        self._open = opener or open_dataset
        self.ds = self._open(self.path)

        self.keys = [str(k) for k in self.ds.variables["key"][:]]
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.zone = int(getattr(self.ds, "utm_zone", 53))
        raw_layers = getattr(self.ds, "layers", [0])
        self.layers = [int(t) for t in np.atleast_1d(raw_layers)]
        self.time_index = int(getattr(self.ds, "time_index", -1))

        self.coords = {}
        for src in ("flow", "wave"):
            if f"{src}_lon" in self.ds.variables:
                self.coords[src] = (
                    np.asarray(self.ds.variables[f"{src}_lon"][:], dtype="f8"),
                    np.asarray(self.ds.variables[f"{src}_lat"][:], dtype="f8"))

    def close(self):
        try:
            self.ds.close()
        except Exception:
            pass

    def has(self, key):
        return key in self.index

    def _values(self, name, n, layer=None):
        """Tranche d'un champ, deja remise a l'echelle."""
        var = self.ds.variables[name]
        raw = var[n] if layer is None else var[n, layer]
        raw = np.asarray(raw)
        scale = float(getattr(var, "scale_factor", 1.0))
        out = raw.astype("float64") * scale
        out[raw == FILL] = np.nan
        return out

    def map_layer(self, key, layer="currents", layer_index=0, **kwargs):
        """Meme charge utile que scenario_field.read_map_layer."""
        spec = sfield.MAP_LAYERS.get(layer)
        if spec is None:
            raise ValueError(f"Unknown map layer '{layer}'.")
        if key not in self.index:
            raise ValueError(f"Scenario '{key}' absent from the compact file.")
        n = self.index[key]

        src = spec["source"]
        if src not in self.coords:
            raise ValueError(f"The compact file holds no {src.upper()} output.")
        plon, plat = self.coords[src]

        if spec["mode"] == "vector":
            if "flow_ue" not in self.ds.variables:
                raise ValueError("No currents in the compact file.")
            li = min(max(0, layer_index), len(self.layers) - 1)
            ue = self._values("flow_ue", n, li)
            vn = self._values("flow_vn", n, li)
            # FILL = maille seche ou run absent ; une valeur nulle mais
            # presente signifie « en eau, courant nul » et doit rester
            # affichee.
            wet = np.isfinite(ue)
            if not wet.any():
                raise ValueError("no FLOW output stored for this run")
            values = np.hypot(np.nan_to_num(ue), np.nan_to_num(vn))
            extra = {"ue": np.nan_to_num(ue), "vn": np.nan_to_num(vn)}
            # Le fichier compact ne contient qu'une partie des couches :
            # on transmet leur numero d'origine pour que l'interface
            # n'affiche pas "couche 2/2" la ou il s'agit de la dixieme.
            axes = [{"dim": "layer", "kind": "layer",
                     "size": len(self.layers), "index": li,
                     "values": [int(t) + 1 for t in self.layers],
                     "total": int(getattr(self.ds, "n_layers_source", 0)) or None}]
        else:
            name = f"wave_{spec['var']}"
            if name not in self.ds.variables:
                raise ValueError(f"'{spec['var']}' absent from the compact file.")
            values = self._values(name, n)
            wet = np.isfinite(values)
            if not wet.any():
                raise ValueError("no WAVE output stored for this run")
            values = np.nan_to_num(values)
            wdir = self._values("wave_dir", n)
            extra = {"dir": np.nan_to_num(wdir)}
            axes = []

        # Un fichier produit avant l'introduction du masque ne contient
        # aucune maille FILL : on repasse alors sur l'heuristique
        # historique plutot que d'echouer.
        has_mask = not bool(wet.all())
        out = sfield.assemble_map(plon, plat, values, spec, extra=extra,
                                  wet=wet if has_mask else None, **kwargs)
        out.update({
            "layer": layer, "zone": self.zone, "source": "compact",
            "axes": axes, "reduction": [],
            "n_valid_cells": int(len(plon)), "n_cells": int(len(plon)),
            "var": spec.get("var") or "U1/V1",
        })
        return out

    def params(self, key):
        n = self.index[key]
        return {p: float(self.ds.variables[p][n])
                for p in ("wind_speed", "wind_dir", "wlvl", "salinity")
                if p in self.ds.variables}
