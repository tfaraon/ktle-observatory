#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garde-fou linguistique : l'interface doit etre entierement en anglais.

Les libelles et avertissements affiches sur le site viennent en partie
du serveur (Python) et en partie du frontend. Il est facile d'en
traduire une moitie et d'oublier l'autre : ce test inspecte les charges
utiles reellement servies, ainsi que les chaines du frontend.

Ce qui reste en francais volontairement — commentaires du code,
docstrings, sorties de terminal des scripts du pipeline — est exclu.

Execution :  python tests/test_language.py
"""

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

# Mots francais courants, en frontieres de mot pour eviter les faux
# positifs ("les" dans "levels", "du" dans "reduced"...).
FRENCH_WORDS = re.compile(
    r"\b(le|la|les|des|du|une|un|dans|avec|pour|sur|aucun|aucune|"
    r"ecart|ecarts|niveau|vitesse|direction du|salinite|vagues|"
    r"donnees|fichier|fichiers|scenario le|plage|simulee|couche|"
    r"mailles|seches|serveur|indisponible|introuvable)\b",
    re.IGNORECASE)
ACCENTS = re.compile(r"[éèêëàâäîïôöûùüçœÉÈÊÀÂÎÔÛÇ]")

# Chaines legitimes malgre un accent ou un mot ambigu
ALLOWED = {"Kati Thanda – Lake Eyre", "Kati Thanda – Lake Eyre · Observatory"}


def offending(text):
    if not isinstance(text, str) or text in ALLOWED:
        return None
    if ACCENTS.search(text):
        return "accent"
    if FRENCH_WORDS.search(text):
        return "mot français"
    return None


def walk(node, path=""):
    """Toutes les chaines d'une charge utile JSON, avec leur chemin."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node[:40]):     # échantillon suffisant
            out += walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        out.append((path, node))
    return out


def check_payload(label, payload, problems):
    for path, text in walk(payload):
        why = offending(text)
        if why:
            problems.append(f"{label}{path} [{why}] {text[:70]}")


# ══════════════════════════════════════════════════════════════
# Charges utiles du serveur
# ══════════════════════════════════════════════════════════════

problems = []

import scenarios as sc  # noqa: E402
import scenario_field as sf  # noqa: E402

# Libellés des paramètres, affichés dans les cartes d'appariement
for key, (_, unit, label) in sc.PARAM_SPECS.items():
    why = offending(label)
    assert not why, f"PARAM_SPECS[{key}] = {label!r} ({why})"

# Libellés de secours des variables, affichés sous les cartes
for key, label in sf.KNOWN_VARS.items():
    why = offending(label)
    assert not why, f"KNOWN_VARS[{key}] = {label!r} ({why})"

# Libellés des couches cartographiques
for key, spec in sf.MAP_LAYERS.items():
    why = offending(spec["label"])
    assert not why, f"MAP_LAYERS[{key}] = {spec['label']!r} ({why})"


def scen(sp, di, wl, sal=250.0):
    return {"key": f"sp{sp}_dir{di}_wl{wl}", "files": {},
            "params": {"wind_speed": sp, "wind_dir": di,
                       "wlvl": wl, "salinity": sal}}


# Avertissements : hors plage (bas et haut) et écart notable
pool = [scen(5.0, 0.0, -13.0), scen(20.0, 180.0, -11.0)]
grid = sc.build_grid(pool)
for target in [
    {"wind_speed": 40.0, "wind_dir": 90.0, "wlvl": -20.0, "salinity": 250.0},
    {"wind_speed": 12.0, "wind_dir": 45.0, "wlvl": -12.0, "salinity": 250.0},
]:
    result = sc.match_scenario(pool, grid, target)
    assert result["warnings"], "au moins un avertissement attendu"
    check_payload("match", result, problems)

# Le libellé du datum est affiché sous le niveau d'eau
import yaml  # noqa: E402

cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
why = offending((cfg.get("display") or {}).get("datum_label", ""))
assert not why, f"display.datum_label ({why})"

# Libellés des couches d'imagerie, affichés sur les boutons
for layer in (cfg.get("imagery") or {}).get("layers", []):
    why = offending(layer.get("label", ""))
    assert not why, f"imagery layer {layer.get('label')!r} ({why})"

# ══════════════════════════════════════════════════════════════
# Messages d'erreur du serveur, affichés tels quels sur la carte
# ══════════════════════════════════════════════════════════════

sys.path.insert(0, str(ROOT / "backend"))
import app as backend  # noqa: E402

client = backend.app.test_client()
for url in ("/api/scenario/maplayer?key=inconnu",
            "/api/scenario/field?key=inconnu",
            "/api/scenario/currents?key=inconnu",
            "/api/scenario/match?wlvl=pasunnombre",
            "/api/health"):
    payload = client.get(url).get_json()
    if payload:
        check_payload(f"GET {url} ", payload, problems)

# ══════════════════════════════════════════════════════════════
# Frontend : texte visible et chaînes affichées
# ══════════════════════════════════════════════════════════════

html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
for text in re.findall(r">([^<>{}]{4,})<", html):
    stripped = text.strip()
    why = offending(stripped)
    if why:
        problems.append(f"index.html [{why}] {stripped[:70]}")

# Les chaînes de app.js, hors commentaires
js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
js_code = re.sub(r"//.*", "", js)
js_code = re.sub(r"/\*(.|\n)*?\*/", "", js_code)
for quoted in re.findall(r'"([^"\n]{6,})"|`([^`\n]{6,})`', js_code):
    text = quoted[0] or quoted[1]
    why = offending(text)
    if why:
        problems.append(f"app.js [{why}] {text[:70]}")

# Le texte de l'onglet Methods
methods = (ROOT / "frontend" / "methods.js").read_text(encoding="utf-8")
methods_text = re.sub(r"<[^>]+>", " ", methods)
methods_text = re.sub(r"^.*?const METHODS_HTML = `", "", methods_text,
                      flags=re.S)
for word in set(FRENCH_WORDS.findall(methods_text)):
    problems.append(f"methods.js [mot français] {word}")
for m in set(ACCENTS.findall(methods_text)):
    problems.append(f"methods.js [accent] {m}")

# ══════════════════════════════════════════════════════════════

if problems:
    print(f"{len(problems)} chaîne(s) non anglaise(s) exposée(s) :")
    for p in problems[:25]:
        print("  " + p)
    raise SystemExit(1)

print("OK — libellés, avertissements, messages d'erreur et frontend "
      "entièrement en anglais.")
