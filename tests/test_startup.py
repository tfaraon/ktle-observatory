#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la commande de premier lancement (startup.py).

Les sous-processus sont remplaces par un substitut : ce qui est
verifie ici, c'est l'enchainement des etapes, pas le contenu de chacune
(couvert par les autres tests).

Verifie :
  - les controles prealables (repertoire des simulations absent,
    aucun site, plan d'experience manquant) ;
  - qu'une etape dont le resultat existe deja est ignoree ;
  - qu'un index de demonstration declenche une reconstruction ;
  - l'ordre des etapes ;
  - qu'un echec de l'index arrete tout, mais qu'un echec meteo ou
    compactage laisse le site demarrer.

Execution :  python tests/test_startup.py
"""

import json
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import startup  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def make_config(with_scenarios=True, with_sites=True, with_design=True):
    base = TMP / f"cfg_{with_scenarios}_{with_sites}_{with_design}"
    base.mkdir(exist_ok=True)
    (base / "Output").mkdir(exist_ok=True)
    (base / "swot").mkdir(exist_ok=True)
    if with_design:
        (base / "lhs.csv").write_text("wind_sp,wind_dir,wlvl,sal\n",
                                      encoding="utf-8")
    cfg = {
        "paths": {"swot_data": str(base / "swot")},
        "sites": ([{"name": "Belt Bay", "lon": 137.028098,
                    "lat": -28.893022}] if with_sites else []),
        "scenarios": {
            "directory": str(base / "Output") if with_scenarios
                         else str(base / "absent"),
            "design_csv": str(base / "lhs.csv") if with_design
                          else str(base / "absent.csv"),
        },
    }
    path = base / "config.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    return path


# ── Contrôles préalables ─────────────────────────────────────
problems, notes = startup.check_config(make_config())
assert problems == [], problems

problems, _ = startup.check_config(make_config(with_scenarios=False))
assert any("simulations introuvable" in p for p in problems), problems

problems, _ = startup.check_config(make_config(with_sites=False))
assert any("aucun site" in p for p in problems), problems

# Le plan d'expérience manquant est un avertissement, pas un blocage
problems, notes = startup.check_config(make_config(with_design=False))
assert problems == [], problems
assert any("plan d'expérience" in n for n in notes), notes

problems, _ = startup.check_config(TMP / "nexistepas.yaml")
assert any("config.yaml introuvable" in p for p in problems), problems

# ── Enchaînement des étapes ──────────────────────────────────
calls = []
codes = {}


def fake_run(cmd, label):
    script = next((c for c in cmd if c.endswith(".py")), cmd[-1])
    name = Path(script).name
    calls.append((name, tuple(cmd)))
    return codes.get(name, 0), 0.5


startup.run = fake_run
startup.subprocess.call = lambda *a, **kw: 0        # serveur

cfg_path = make_config()
data_dir = TMP / "data"
data_dir.mkdir(exist_ok=True)
startup.DATA = data_dir


def reset(index_demo=None, with_swot=False, with_compact=False):
    calls.clear()
    codes.clear()
    for f in data_dir.glob("*"):
        f.unlink()
    if index_demo is not None:
        (data_dir / "scenarios.json").write_text(
            json.dumps({"demo": index_demo, "scenarios": []}),
            encoding="utf-8")
    if with_swot:
        (data_dir / "swot_wse.json").write_text("{}", encoding="utf-8")
    if with_compact:
        (data_dir / "compact.nc").write_bytes(b"x")


def invoke(*extra):
    sys.argv = ["startup.py", "--config", str(cfg_path)] + list(extra)
    return startup.main()


# Premier lancement complet : les quatre étapes, dans l'ordre
reset()
assert invoke("--no-serve") == 0
order = [c[0] for c in calls]
assert order == ["update_swot.py", "fetch_weather.py", "scenario_index.py",
                 "compact.py"], order
# Le téléchargement est demandé par défaut
assert "--download" in dict(calls)["update_swot.py"]
# Les couches par défaut sont la première et la dixième
assert "0,9" in dict(calls)["compact.py"]

# --skip-download : extraction seule
reset()
invoke("--no-serve", "--skip-download")
assert "--download" not in dict(calls)["update_swot.py"]

# Résultats déjà présents : étapes ignorées
reset(index_demo=False, with_swot=True, with_compact=True)
invoke("--no-serve")
assert [c[0] for c in calls] == ["fetch_weather.py"], calls

# --force refait tout
reset(index_demo=False, with_swot=True, with_compact=True)
invoke("--no-serve", "--force")
assert [c[0] for c in calls] == ["update_swot.py", "fetch_weather.py",
                                 "scenario_index.py", "compact.py"]

# Index de démonstration : reconstruit même s'il existe
reset(index_demo=True, with_swot=True, with_compact=True)
invoke("--no-serve")
assert "scenario_index.py" in [c[0] for c in calls], calls

# Compactage interrompu : la reprise est demandée
reset(index_demo=False, with_swot=True)
(data_dir / "compact.nc").write_bytes(b"x")
invoke("--no-serve", "--force")
assert "--resume" in dict(calls)["compact.py"]

# ── Gestion des échecs ───────────────────────────────────────
# Index en échec -> arrêt, le compactage n'est pas tenté
reset()
codes["scenario_index.py"] = 1
assert invoke("--no-serve") == 1
assert "compact.py" not in [c[0] for c in calls]

# Météo en échec -> simple avertissement, la suite se déroule
reset()
codes["fetch_weather.py"] = 1
assert invoke("--no-serve") == 0
assert "compact.py" in [c[0] for c in calls]

# Compactage en échec -> avertissement, le site peut démarrer
reset()
codes["compact.py"] = 1
assert invoke("--no-serve") == 0

# SWOT en échec -> étape essentielle, arrêt
reset()
codes["update_swot.py"] = 1
assert invoke("--no-serve") == 1

# ── Options de saut ──────────────────────────────────────────
reset()
invoke("--no-serve", "--skip-swot", "--skip-weather", "--skip-compact")
assert [c[0] for c in calls] == ["scenario_index.py"], calls

print("OK — contrôles préalables, ordre des étapes, reprise, détection "
      "de l'index de démonstration et gestion des échecs validés.")
