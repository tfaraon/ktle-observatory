#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base de scenarios Delft3D : indexation par nom de fichier et
appariement aux conditions courantes (BOM + SWOT).

Convention de nommage (le separateur decimal est un underscore) :
    Output/Wave/wave_wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc
    Output/Flow/     wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc
                          ^^^         ^^^      ^^^^     ^^^^^
                          1.0 m/s     0.0 deg  -7.0 m   250.0

Les deux fichiers d'un meme jeu de parametres (sortie WAVE et sortie
FLOW) sont regroupes en un seul scenario. La notation pointee
(wind-sp29.0) reste acceptee.

Ce module ne lit aucun NetCDF : il ne manipule que des noms de
fichiers, ce qui le rend testable sans donnees.
"""

import math
import os
import re
from pathlib import Path

# Cle interne -> (motif dans le nom de fichier, unite, libelle)
PARAM_SPECS = {
    "wind_speed": ("wind-sp", "m/s", "Vitesse du vent"),
    "wind_dir": ("wind-dir", "°", "Direction du vent"),
    "wlvl": ("wlvl", "m", "Niveau d'eau"),
    "salinity": ("sal", "g/L", "Salinité"),
}

# Colonnes du plan d'experience (lhs_all.csv) -> cles internes
CSV_COLUMNS = {
    "wind_sp": "wind_speed",
    "wind_dir": "wind_dir",
    "wlvl": "wlvl",
    "sal": "salinity",
}

# Nombre avec separateur decimal '.' ou '_' (1_0, -7_0, 29.0, 250_0)
NUMBER = r"(-?\d+(?:[._]\d+)?)"

WAVE_PREFIX = "wave_"

# Entetes valides : NetCDF3 classique / 64 bits / CDF-5, et HDF5 (NetCDF4)
NETCDF_MAGIC = (b"CDF\x01", b"CDF\x02", b"CDF\x05", b"\x89HDF")

# Fichiers parasites a ignorer. Les "._nom.nc" sont des AppleDouble :
# macOS les cree en copiant vers un volume non-HFS (exFAT, FAT, reseau).
# Ils portent le meme nom que le fichier utile mais ne contiennent que
# des metadonnees — d'ou un "Unknown file format" a la lecture.
JUNK_DIRS = {"__MACOSX", ".Trashes", ".Spotlight-V100", ".fseventsd"}


def is_junk_path(path, root=None):
    """Fichier systeme (AppleDouble, dossier cache) a ne pas indexer."""
    p = Path(path)
    if p.name.startswith("._") or p.name.startswith("."):
        return True
    parts = p.relative_to(root).parts[:-1] if root else p.parts[:-1]
    return any(part in JUNK_DIRS or part.startswith(".") for part in parts)


def looks_like_netcdf(path):
    """Verifie l'entete du fichier (4 premiers octets)."""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return False
    return any(head.startswith(m) for m in NETCDF_MAGIC)


def to_float(text):
    """'1_0' -> 1.0 ; '-7_0' -> -7.0 ; '29.0' -> 29.0"""
    return float(text.replace("_", "."))


def build_regex(params=None, wlvl_sign="negative"):
    """Construit le motif de lecture des noms de fichiers.

    wlvl_sign="negative" : "wlvl-7_0" -> -7.0 (le tiret est le signe)
    wlvl_sign="positive" : "wlvl-7_0" ->  7.0 (le tiret est un separateur)
    """
    params = params or list(PARAM_SPECS)
    parts = {}
    for key in params:
        token = PARAM_SPECS[key][0]
        if key == "wlvl" and wlvl_sign == "positive":
            parts[key] = re.compile(re.escape(token) + r"-?(\d+(?:[._]\d+)?)")
        else:
            parts[key] = re.compile(re.escape(token) + NUMBER)
    return parts


def parse_scenario_filename(name, regexes):
    """Nom de fichier -> {param: valeur} ou None si incomplet."""
    stem = os.path.basename(name)
    out = {}
    for key, rx in regexes.items():
        m = rx.search(stem)
        if not m:
            return None
        out[key] = to_float(m.group(1))
    return out


def scenario_key(filename):
    """Signature commune aux sorties WAVE et FLOW d'un meme run."""
    stem = Path(filename).stem
    return stem[len(WAVE_PREFIX):] if stem.startswith(WAVE_PREFIX) else stem


def classify_source(path):
    """'wave' ou 'flow', d'apres le prefixe puis le dossier parent."""
    p = Path(path)
    if p.name.startswith(WAVE_PREFIX):
        return "wave"
    parents = [q.name.lower() for q in p.parents[:3]]
    if any("wave" in q for q in parents):
        return "wave"
    if any("flow" in q for q in parents):
        return "flow"
    return "flow"


def scan_directory(directory, regexes, suffix=".nc", verify_format=True):
    """Parcourt recursivement (Output/Wave, Output/Flow...) et regroupe
    les sorties WAVE et FLOW d'un meme jeu de parametres.

    Ecarte les fichiers systeme macOS (._*) et, si verify_format, tout
    fichier dont l'entete n'est pas un NetCDF valide.

    Retourne (scenarios, rapport) ou rapport detaille les exclusions.
    """
    root = Path(directory)
    if not root.exists():
        raise ValueError(f"Répertoire de scénarios introuvable : {directory}")

    grouped = {}
    report = {"unnamed": [], "junk": [], "bad_format": []}

    for path in sorted(root.rglob("*" + suffix)):
        rel = str(path.relative_to(root))
        if is_junk_path(path, root):
            report["junk"].append(rel)
            continue
        params = parse_scenario_filename(path.name, regexes)
        if params is None:
            report["unnamed"].append(rel)
            continue
        if verify_format and not looks_like_netcdf(path):
            report["bad_format"].append(rel)
            continue
        key = scenario_key(path.name)
        entry = grouped.setdefault(key, {"key": key, "params": params,
                                         "files": {}})
        entry["files"][classify_source(path)] = str(path)

    scenarios = [grouped[k] for k in sorted(grouped)]
    return scenarios, report


def build_grid(scenarios):
    """Valeurs distinctes disponibles pour chaque parametre (triees)."""
    grid = {}
    for key in PARAM_SPECS:
        vals = sorted({s["params"][key] for s in scenarios
                       if key in s["params"]})
        if vals:
            grid[key] = vals
    return grid


# ------------------------------------------------------------------
# Appariement
# ------------------------------------------------------------------

def circular_delta(a, b):
    """Ecart angulaire signe minimal (deg), dans [-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def median_step(values):
    """Pas median de la grille (1.0 si une seule valeur)."""
    if len(values) < 2:
        return 1.0
    steps = [b - a for a, b in zip(values, values[1:]) if b > a]
    if not steps:
        return 1.0
    steps.sort()
    mid = len(steps) // 2
    return steps[mid] if len(steps) % 2 else (steps[mid - 1] + steps[mid]) / 2


def build_scales(grid, mode="range"):
    """Echelle de normalisation par parametre.

    mode="range" : etendue du plan d'experience — adapte a un tirage
        LHS, ou le voisin le plus proche peut etre eloigne sur
        plusieurs axes a la fois.
    mode="step"  : pas median — adapte a une grille factorielle
        complete et reguliere.

    La direction du vent est toujours ramenee a 180 deg (ecart maximal
    possible), puisqu'elle est circulaire.
    """
    scales = {}
    for key, vals in grid.items():
        if key == "wind_dir":
            scales[key] = 180.0
        elif mode == "step":
            scales[key] = median_step(vals) or 1.0
        else:
            span = (vals[-1] - vals[0]) if len(vals) > 1 else 0.0
            scales[key] = span if span > 0 else 1.0
    return scales


def candidate_pool(scenarios, target, wlvl_mode="nearest", tol=1e-6):
    """Scenarios eligibles a l'appariement.

    wlvl_mode="down" n'autorise que les niveaux INFERIEURS OU EGAUX au
    niveau observe. Retenir un scenario plus haut simulerait plus
    d'eau qu'il n'y en a : a -12.91 m sur un fond vers -15.2 m, passer
    a -12.0 m ajoute pres de 40 % de tirant d'eau, ce qui modifie la
    dissipation des vagues et les vitesses. Choisir vers le bas laisse
    l'erreur du cote conservateur.

    Retourne (pool, limite_appliquee).
    """
    if wlvl_mode != "down" or target.get("wlvl") is None:
        return scenarios, False
    limit = target["wlvl"] + tol
    below = [s for s in scenarios
             if s["params"].get("wlvl") is not None
             and s["params"]["wlvl"] <= limit]
    # Si tous les scenarios sont au-dessus du niveau observe, mieux vaut
    # le plus proche que rien : le controle d'enveloppe le signalera.
    return (below, True) if below else (scenarios, False)


def match_scenario(scenarios, grid, target, weights=None, mode="range",
                   n_alternatives=4, wlvl_mode="nearest"):
    """Scenario le plus proche des conditions cibles.

    La distance est normalisee par l'echelle de chaque parametre
    (comparer des m/s a des degres n'a pas de sens sinon) ; la
    direction du vent est traitee circulairement.

    Retourne None si aucun scenario, sinon un dict :
        scenario      entree retenue
        deltas        ecart par parametre (unites physiques, signe)
        distance      distance normalisee totale
        envelope      par parametre : "in" | "below" | "above"
        warnings      messages lisibles (hors enveloppe, ecart important)
        alternatives  scenarios suivants, par distance croissante
    """
    if not scenarios:
        return None
    weights = weights or {}
    scales = build_scales(grid, mode)
    pool, wlvl_capped = candidate_pool(scenarios, target, wlvl_mode)

    def deltas_of(params):
        out = {}
        for key, value in target.items():
            if key not in params or value is None:
                continue
            out[key] = (circular_delta(value, params[key]) if key == "wind_dir"
                        else value - params[key])
        return out

    def distance(params):
        total = 0.0
        for key, d in deltas_of(params).items():
            total += (weights.get(key, 1.0) * d / scales.get(key, 1.0)) ** 2
        return math.sqrt(total)

    ranked = sorted(pool, key=lambda s: distance(s["params"]))
    best = ranked[0]
    params = best["params"]
    deltas = {k: round(v, 3) for k, v in deltas_of(params).items()}

    envelope, warnings = {}, []
    for key, value in target.items():
        if key not in params or value is None:
            continue
        vals = grid.get(key, [])
        label, unit = PARAM_SPECS[key][2], PARAM_SPECS[key][1]

        if key == "wind_dir":
            envelope[key] = "in"  # grandeur circulaire : jamais hors bornes
        elif vals and value < vals[0]:
            envelope[key] = "below"
            warnings.append(f"{label} ({value:g} {unit}) sous la plage "
                            f"simulée [{vals[0]:g} – {vals[-1]:g} {unit}]")
        elif vals and value > vals[-1]:
            envelope[key] = "above"
            warnings.append(f"{label} ({value:g} {unit}) au-dessus de la plage "
                            f"simulée [{vals[0]:g} – {vals[-1]:g} {unit}]")
        else:
            envelope[key] = "in"

        # Ecart notable au sein de la plage : le plan est lacunaire ici
        d = abs(deltas.get(key, 0.0))
        if key == "wlvl" and wlvl_capped:
            continue        # ecart voulu : on n'a garde que les niveaux bas
        if envelope[key] == "in" and d > 0.12 * scales.get(key, 1.0):
            warnings.append(f"{label} : écart de {d:.1f} {unit} "
                            f"avec le scénario le plus proche")

    alternatives = [{
        "key": s["key"],
        "params": s["params"],
        "distance": round(distance(s["params"]), 3),
        "deltas": {k: round(v, 3) for k, v in deltas_of(s["params"]).items()},
    } for s in ranked[1:1 + n_alternatives]]

    return {
        "scenario": best,
        "deltas": deltas,
        "distance": round(distance(params), 3),
        "wlvl_capped": bool(wlvl_capped),
        "envelope": envelope,
        "scales": {k: round(v, 3) for k, v in scales.items()},
        "mode": mode,
        "warnings": warnings,
        "alternatives": alternatives,
    }


# ------------------------------------------------------------------
# Plan d'experience (lhs_all.csv)
# ------------------------------------------------------------------

def read_design(path):
    """Lit le plan d'experience -> liste de {param: valeur}."""
    import csv

    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            row = {}
            for col, key in CSV_COLUMNS.items():
                if col in raw and raw[col] not in (None, ""):
                    row[key] = float(raw[col])
            if row:
                rows.append(row)
    return rows


def _signature(params, ndigits=3):
    return tuple(round(params.get(k, float("nan")), ndigits)
                 for k in PARAM_SPECS)


def design_coverage(design, scenarios):
    """Compare le plan d'experience aux fichiers reellement presents.

    Retourne le nombre de runs prevus, realises, manquants (avec un
    echantillon), et les fichiers hors plan.
    """
    have = {}
    for s in scenarios:
        have.setdefault(_signature(s["params"]), []).append(s)

    wanted, missing = set(), []
    for row in design:
        sig = _signature(row)
        wanted.add(sig)
        if sig not in have:
            missing.append(row)

    extra = [s["key"] for sig, group in have.items() if sig not in wanted
             for s in group]

    return {
        "n_design": len(design),
        "n_design_unique": len(wanted),
        "n_done": len(wanted) - len(missing),
        "n_missing": len(missing),
        "missing_sample": missing[:10],
        "n_extra": len(extra),
        "extra_sample": extra[:10],
    }
