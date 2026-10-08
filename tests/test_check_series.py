#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du garde-fou de publication (tools/check_series.py).

Depuis que les chaines SWOT sont incrementales, la serie complete n'est
plus deductible des granules presents : un cache perdu donne un calcul
reussi mais une serie amputee. Ce garde-fou est la seule chose qui
distingue les deux. Il doit donc etre juste dans les deux sens : bloquer
une serie plus courte, et ne jamais bloquer une mise a jour normale.

Verifie, dans un depot Git jetable :
  - comptage des observations sur les deux formes de JSON (serie a la
    racine, series par site) ;
  - serie plus longue ou egale : publication autorisee ;
  - serie plus courte : publication refusee, avec les chiffres ;
  - fichier nouveau ou absent : pas de blocage ;
  - JSON illisible : refus ;
  - comparaison a une autre reference que HEAD.

Execution :  python tests/test_check_series.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_series as cs          # noqa: E402

# ── Comptage, independamment de la forme ────────────────────
assert cs.count_observations({"series": [1, 2, 3]}) == 3
assert cs.count_observations(
    {"sites": [{"series": [1, 2]}, {"series": [3]}]}) == 3
assert cs.count_observations({"series": []}) == 0
assert cs.count_observations({"stats": {"n": 99}}) == 0, \
    "seul « series » compte, pas un total annonce"
assert cs.count_observations([{"series": [1]}, {"series": [2, 3]}]) == 3


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def write(path, n):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"series": [{"date": i} for i in range(n)]}),
                    encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    repo = Path(td)
    git("init", "-q", cwd=repo)
    git("config", "user.email", "t@t", cwd=repo)
    git("config", "user.name", "t", cwd=repo)

    rel = "site/data/lake_area.json"
    target = repo / rel
    write(target, 100)
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "base", cwd=repo)

    cs.ROOT = repo                 # le module travaille dans ce dépôt

    # Inchangé, puis allongé : rien à signaler
    assert cs.check([rel]) == []
    write(target, 101)
    assert cs.check([rel]) == []

    # Raccourci : refus, avec les deux chiffres
    write(target, 42)
    losses = cs.check([rel])
    assert losses == [(rel, 100, 42)], losses

    # Fichier absent, et fichier non versionné : pas de blocage
    assert cs.check(["site/data/absent.json"]) == []
    new = "site/data/rivers.json"
    write(repo / new, 7)
    assert cs.check([new]) == []

    # JSON illisible : refus
    target.write_text("{ pas du json", encoding="utf-8")
    bad = cs.check([rel])
    assert len(bad) == 1 and "illisible" in str(bad[0][2]), bad

    # Comparaison à une autre référence
    write(target, 100)
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "deux", cwd=repo)
    git("branch", "-f", "repere", cwd=repo)
    write(target, 99)
    assert cs.check([rel], ref="repere") == [(rel, 100, 99)]
    assert cs.check([rel], ref="inconnu") == [], \
        "une référence absente ne doit pas bloquer la publication"

print("OK — séries plus courtes bloquées, mises à jour normales et "
      "fichiers neufs laissés passer, référence de comparaison réglable.")
