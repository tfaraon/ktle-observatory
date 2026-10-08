#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coherence des workflows GitHub Actions avec le code et entre eux.

Les workflows sont la seule chose qui fasse vivre le site quand aucune
machine n'est allumee. Une derive y est invisible : un nom de variable
change dans le code, le workflow continue a tourner et publie des
donnees figees. Ce test verifie :

  - YAML valide, declencheur planifie, lancement manuel possible ;
  - chaque workflow qui pousse demande la permission contents: write ;
  - les variables d'environnement du workflow SWOT sont bien celles que
    lit le code (KTLE_SWOT_DIR, KTLE_STATE_DIR) ;
  - le workflow SWOT refuse de tourner sans l'etat versionne, et
    verifie la longueur de la serie avant de publier ;
  - aucun secret en clair, aucun chemin du disque externe ;
  - les horaires planifies ne se chevauchent pas, et les series
    publiees ont une regle de fusion dans .gitattributes.

Execution :  python tests/test_workflows.py
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"

flows = {p.name: yaml.safe_load(p.read_text(encoding="utf-8"))
         for p in sorted(WF.glob("*.yml"))}
texts = {p.name: p.read_text(encoding="utf-8") for p in sorted(WF.glob("*.yml"))}
assert "swot.yml" in flows, sorted(flows)

# ── Forme commune ────────────────────────────────────────────
# PyYAML lit « on: » comme le booleen True : la cle est donc True.
def triggers(flow):
    return flow.get("on") or flow.get(True) or {}

scheduled = {}
for name, flow in flows.items():
    trig = triggers(flow)
    assert trig, f"{name} : aucun déclencheur"
    if "schedule" in trig:
        crons = [s["cron"] for s in trig["schedule"]]
        assert "workflow_dispatch" in trig, \
            f"{name} : planifié mais non lançable à la main"
        for c in crons:
            fields = c.split()
            assert len(fields) == 5, f"{name} : cron invalide « {c} »"
        scheduled[name] = crons

# Tout workflow qui commite doit demander l'ecriture
for name, flow in flows.items():
    if "git push" in texts[name]:
        perms = flow.get("permissions") or {}
        assert perms.get("contents") == "write", f"{name} : contents: write manquant"

# ── Pas de secret ni de chemin local ─────────────────────────
for name, text in texts.items():
    assert "/Volumes/" not in text, f"{name} : chemin du disque externe"
    for key, value in re.findall(
            r"(?i)(password|api_key|[a-z-]*token)\s*[:=]\s*(\S+)", text):
        # « id-token: write » est une permission, pas un secret.
        if value in ("write", "read", "none", "|", ">", "''", '""'):
            continue
        assert value.startswith("${{") or value.startswith('"${{'), \
            f"{name} : {key} en clair"

# ── Le workflow SWOT ─────────────────────────────────────────
swot = flows["swot.yml"]
text = texts["swot.yml"]
job = swot["jobs"]["refresh"]
env = job["env"]

# Les noms doivent etre ceux que le code lit : sans cela le workflow
# ecrirait dans data/ et telechargerait dans le depot.
code = (ROOT / "pipeline" / "update_swot.py").read_text(encoding="utf-8")
for var in ("KTLE_SWOT_DIR", "KTLE_STATE_DIR"):
    assert var in env, f"swot.yml : {var} absent"
    assert f'environ.get("{var}")' in code, f"{var} n'est lu par aucun code"
assert "runner.temp" in env["KTLE_SWOT_DIR"], \
    "les granules doivent aller dans le temporaire du runner, pas dans le dépôt"
assert env["KTLE_STATE_DIR"] == "state", env["KTLE_STATE_DIR"]
for var in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"):
    assert "secrets." + var in env[var], f"{var} doit venir des secrets"

steps = job["steps"]
names = [s.get("name", "") for s in steps]
run_all = "\n".join(s.get("run", "") for s in steps)

# Garde-fou : sans l'etat versionne, la serie serait reconstruite sur
# les seuls granules du jour, et l'historique du site ecrase.
guard = next(s for s in steps if "state" in s.get("name", "").lower())
assert "exit 1" in guard["run"], "swot.yml : le garde-fou ne bloque pas"
assert steps.index(guard) < min(
    i for i, s in enumerate(steps) if "update_swot.py" in s.get("run", "")), \
    "le garde-fou doit précéder le téléchargement"

# Verification avant publication, et publication en dernier
assert any("sanity" in n.lower() or "vérif" in n.lower() for n in names), names
assert "git push" in steps[-1].get("run", ""), "la publication doit être la dernière étape"
# Le garde-fou contre une serie amputee est un script teste, pas du
# shell inline : il doit couvrir les trois series publiees ici.
guard_step = next(s for s in steps
                  if "check_series.py" in s.get("run", ""))
assert steps.index(guard_step) == len(steps) - 2, \
    "la vérification doit précéder immédiatement la publication"
for series in ("swot_wse.json", "lake_area.json", "water_extent.json"):
    assert series in guard_step["run"], f"{series} non vérifié"
assert (ROOT / "tools" / "check_series.py").exists()

# Les trois chaines, dans l'ordre : niveaux, surface, etendue
order = [run_all.index(s) for s in
         ("update_swot.py", "lake_area.py", "water_extent.py")]
assert order == sorted(order), "ordre des chaînes SWOT inversé"
# L'etendue depend d'une bathymetrie qui peut ne pas etre versionnee
assert "bathymetry.npz" in run_all

# Le pilote de fusion doit etre declare avant tout pull
push_step = steps[-1]["run"]
assert push_step.index("merge.keepnew.driver") < push_step.index("git pull"), \
    "pilote de fusion déclaré après le pull"

# ── Series publiees et regles de fusion ──────────────────────
attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
for name, text in texts.items():
    for series in re.findall(r"site/data/(\w+\.json)", text):
        assert f"site/data/{series}" in attrs, \
            f"{name} publie {series} sans règle de fusion"
for folder in re.findall(r"site/data/(\w+_maps)", "\n".join(texts.values())):
    assert f"site/data/{folder}/*.png" in attrs, f"{folder} sans règle de fusion"
assert "state/*.json" in attrs, "l'état versionné doit avoir une règle de fusion"

# ── Horaires : pas deux chaines a la meme minute ─────────────
slots = [(c, n) for n, crons in scheduled.items() for c in crons
         if not c.startswith("0 *") and "*" not in c.split()[1]]
assert len({c for c, _ in slots}) == len(slots), f"horaires en double : {slots}"

print(f"OK — {len(flows)} workflows : déclencheurs valides, SWOT sans disque "
      f"externe, état versionné exigé avant publication, {len(slots)} créneaux "
      "quotidiens distincts, séries couvertes par .gitattributes.")
