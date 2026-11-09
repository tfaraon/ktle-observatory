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
    assert var in text, f"swot.yml : {var} absent"
    assert f'environ.get("{var}")' in code, f"{var} n'est lu par aucun code"
# KTLE_SWOT_DIR est pose dans une etape, via $GITHUB_ENV : au niveau du
# job, le contexte « runner » n'existe pas encore.
assert "KTLE_SWOT_DIR" not in env, \
    "KTLE_SWOT_DIR au niveau du job : il lui faut le temporaire du runner"
assert 'KTLE_SWOT_DIR=$RUNNER_TEMP' in text and '$GITHUB_ENV' in text, \
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

# ── Contextes autorises dans « env » au niveau du job ────────
# Le contexte « runner » n'existe pas encore quand GitHub evalue
# jobs.<id>.env : un ${{ runner.temp }} a cet endroit rend le fichier
# invalide, aucune execution n'est creee, et le seul symptome visible
# est un workflow affiche par son chemin au lieu de son nom. Ce test a
# ete ecrit apres que ce defaut a fige la chaine SWOT pendant un mois.
FORBIDDEN_AT_JOB_LEVEL = ("runner.", "job.", "steps.", "env.")
for name, flow in flows.items():
    for job_id, job in (flow.get("jobs") or {}).items():
        for key, value in (job.get("env") or {}).items():
            for ctx in FORBIDDEN_AT_JOB_LEVEL:
                assert "${{ " + ctx not in str(value), (
                    f"{name} : {job_id}.env.{key} utilise le contexte "
                    f"« {ctx.rstrip('.')} », indisponible au niveau du job ; "
                    "posez-le dans une étape, via $GITHUB_ENV")

# ── Publication apres une chaine de donnees ──────────────────
# Une poussee faite avec le GITHUB_TOKEN ne declenche aucun autre
# workflow : sans « workflow_run », le site publie reste celui de la
# derniere poussee humaine, pendant que les chaines verdissent.
pages = flows["pages.yml"]
trig = triggers(pages)
assert "workflow_run" in trig, \
    "pages.yml doit se déclencher à la fin des chaînes de données"
watched = set(trig["workflow_run"]["workflows"])
pushers = {flow.get("name") for n, flow in flows.items()
           if "git push" in texts[n] and n != "pages.yml"}
assert pushers <= watched, (
    "chaînes qui publient sans réveiller « Deploy site » : "
    f"{sorted(pushers - watched)}")
assert watched <= {f.get("name") for f in flows.values()}, (
    f"« workflow_run » nomme un workflow inexistant : "
    f"{sorted(watched - {f.get('name') for f in flows.values()})}")
# Ne pas republier apres une chaine en echec
job = pages["jobs"]["deploy"]
assert "workflow_run.conclusion" in str(job.get("if", "")), \
    "pages.yml publie même après une chaîne en échec"
# Un deploiement en cours ne doit pas etre interrompu par le suivant
assert pages["concurrency"]["cancel-in-progress"] is False, \
    "une publication interrompue laisse le site dans l'état précédent"

# ── Horaires : pas deux chaines a la meme minute ─────────────
slots = [(c, n) for n, crons in scheduled.items() for c in crons
         if not c.startswith("0 *") and "*" not in c.split()[1]]
assert len({c for c, _ in slots}) == len(slots), f"horaires en double : {slots}"

print(f"OK — {len(flows)} workflows : déclencheurs valides, SWOT sans disque "
      f"externe, état versionné exigé avant publication, {len(slots)} créneaux "
      "quotidiens distincts, séries couvertes par .gitattributes.")

# ── Ce qu'un workflow installe couvre ce que ses scripts importent ──
#
# swot.yml a telecharge douze minutes de granules avant de tomber sur
# « No module named 'rasterio' ». Le module figurait dans
# requirements.txt, commentaire a l'appui, mais la ligne pip du workflow
# etait ecrite a la main et ne le mentionnait pas. Deux listes pour une
# seule verite derivent toujours ; ce test fait echouer la derive ici
# plutot qu'apres un telechargement.

import ast as _ast
import sys as _sys

# Nom importe -> nom distribue, quand ils different
DIST = {"PIL": "Pillow", "yaml": "PyYAML", "cv2": "opencv-python",
        "dateutil": "python-dateutil", "sklearn": "scikit-learn"}

_STD = set(_sys.stdlib_module_names)
_REPO_PY = {p.stem: p for p in ROOT.rglob("*.py")
            if ".git" not in p.parts and "tests" not in p.parts}
# Les paquets du depot comptent comme locaux : SWOT_toolbox est un
# dossier avec __init__.py, pas un fichier, et serait sinon pris pour
# une dependance a installer.
_REPO_PY.update({d.name: d / "__init__.py" for d in ROOT.iterdir()
                 if d.is_dir() and (d / "__init__.py").exists()})


def _optional(tree):
    """Ids des noeuds sous un try/except ImportError.

    C'est le signal explicite qu'une dependance est facultative :
    SWOT_toolbox importe ainsi son module de cartographie, inutile cote
    serveur. Les compter reviendrait a exiger geopandas et matplotlib
    sur un runner qui ne trace rien.
    """
    skip = set()
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Try):
            continue
        if any(h.type is None or "ImportError" in _ast.dump(h.type)
               for h in node.handlers):
            for stmt in node.body:
                for sub in _ast.walk(stmt):
                    skip.add(id(sub))
    return skip


def _imports(path, seen):
    """Modules tiers importes par un script, imports locaux suivis."""
    if path in seen:
        return set()
    seen.add(path)
    try:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    skip = _optional(tree)
    out = set()
    for node in _ast.walk(tree):
        if id(node) in skip:
            continue
        names = []
        if isinstance(node, _ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, _ast.ImportFrom):
            if node.level:                      # from . import X
                pkg = path.parent
                names = [a.name.split(".")[0] for a in node.names]
                for n in names:
                    f = pkg / f"{n}.py"
                    if f.exists():
                        out |= _imports(f, seen)
                continue
            if node.module:
                names = [node.module.split(".")[0]]
        for n in names:
            if n in _STD:
                continue
            local = _REPO_PY.get(n)
            if local is not None:
                out |= _imports(local, seen)
            else:
                out.add(n)
    return out


_req = {ln.split("#")[0].strip().lower()
        for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if ln.split("#")[0].strip()}

_gaps = []
for name, text in texts.items():
    installed = set()
    for line in text.splitlines():
        if "pip install" not in line:
            continue
        arg = line.split("pip install", 1)[1].strip()
        if arg.startswith("-r "):
            installed |= _req
        else:
            installed |= {w.lower() for w in arg.split() if not w.startswith("-")}
    if not installed:
        continue
    needed = set()
    for line in text.splitlines():
        for tok in line.split():
            if tok.endswith(".py") and (ROOT / tok).exists():
                needed |= _imports(ROOT / tok, set())
    for mod in sorted(needed):
        if DIST.get(mod, mod).lower() not in installed:
            _gaps.append(f"{name} exécute un script qui importe « {mod} » "
                         f"sans l'installer")

assert not _gaps, "\n  ".join([""] + _gaps)
print(f"OK — chaque workflow installe ce que ses scripts importent "
      f"({len(texts)} workflows vérifiés).")
