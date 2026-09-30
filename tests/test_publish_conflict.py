#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conflits de donnees entre cette machine et le workflow GitHub.

Les deux calculent chaque jour les memes fichiers : JSON de donnees et
cartes de pluie. Git ne sait pas fusionner deux PNG, et une regle de
.gitattributes doit donc remplacer le fichier plutot que le fusionner.
Une macro « binary » placee apres merge=ours annulerait cette regle :
c'est ce qui a bloque une publication, d'ou ce test.

Il rejoue la situation dans un depot jetable : les fichiers declares se
resolvent seuls, et deploy/resolve_conflicts.sh termine le rebase quand
un fichier de donnees echappe aux regles, mais refuse de toucher a un
conflit de code.

Execution :  python tests/test_publish_conflict.py
"""

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATTRS = (ROOT / ".gitattributes").read_text(encoding="utf-8")
RESOLVER = ROOT / "deploy" / "resolve_conflicts.sh"


def git(cmd, cwd, check=True):
    r = subprocess.run(f"git {cmd}", cwd=cwd, shell=True, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {cmd}\n{r.stdout}\n{r.stderr}")
    return r


# ── Aucune macro « binary » ne doit suivre merge=ours ──
for line in ATTRS.splitlines():
    if line.strip().startswith("#") or "merge=keepnew" not in line:
        continue
    attrs = line.split()[1:]
    assert "binary" not in attrs, f"« binary » annule la règle : {line}"

declared = [l.split()[0] for l in ATTRS.splitlines()
            if l.strip() and not l.strip().startswith("#")]
assert any("rain_maps" in d for d in declared), declared


def repo(files_local, files_remote, attrs=ATTRS):
    """Depot ou un commit distant et un commit local touchent les memes fichiers."""
    td = Path(tempfile.mkdtemp())
    work, remote = td / "work", td / "remote.git"
    git(f"init -q --bare {remote}", td)
    git(f"clone -q {remote} {work}", td)
    git("config user.email t@t && git config user.name t", work)
    git("config merge.keepnew.driver 'cp -f %B %A'", work)
    (work / ".gitattributes").write_text(attrs, encoding="utf-8")
    for f in set(files_local) | set(files_remote):
        p = work / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"BASE")
    git("add -A && git commit -qm base && git push -q origin HEAD", work)
    # Le workflow GitHub publie sa version
    clone = td / "bot"
    git(f"clone -q {remote} {clone}", td)
    git("config user.email b@b && git config user.name b", clone)
    for f, data in files_remote.items():
        (clone / f).write_bytes(data)
    git("add -A && git commit -qm bot && git push -q origin HEAD", clone)
    # Cette machine publie la sienne
    for f, data in files_local.items():
        (work / f).write_bytes(data)
    git("add -A && git commit -qm local", work)
    return work


# ── Cas réel : mêmes cartes et mêmes JSON des deux côtés ──
files = {"site/data/rain_maps/sum7.png": b"\x89PNG-local", "site/data/rainfall.json": b'{"a": 1}'}
bot = {"site/data/rain_maps/sum7.png": b"\x89PNG-bot", "site/data/rainfall.json": b'{"a": 2}'}
work = repo(files, bot)
r = git("pull --rebase --autostash", work, check=False)
assert r.returncode == 0, f"la règle doit résoudre seule :\n{r.stdout}\n{r.stderr}"
assert (work / "site/data/rain_maps/sum7.png").read_bytes() == b"\x89PNG-local", "version locale gardée"
assert git("push -q origin HEAD", work).returncode == 0

# ── Règle absente du dépôt distant, comme pendant un rebase qui la rejoue ──
# Le filet de sécurité termine alors le rebase, depuis une copie du script
# placée hors du dépôt, puisque l'arbre de travail ne la contient pas encore.
work = repo({"site/data/extra.bin": b"local"}, {"site/data/extra.bin": b"bot"})
r = git("pull --rebase --autostash", work, check=False)
assert r.returncode != 0 and "CONFLICT" in (r.stdout + r.stderr)
copy = Path(tempfile.mkdtemp()) / "resolve.sh"
copy.write_bytes(RESOLVER.read_bytes())
copy.chmod(0o755)
out = subprocess.run([str(copy)], cwd=work, capture_output=True, text=True)
assert out.returncode == 0, out.stdout + out.stderr
assert "données seules" in out.stdout
assert (work / "site/data/extra.bin").read_bytes() == b"local", "version calculée ici gardée"
assert not git("status --porcelain", work).stdout.strip(), "rebase terminé, arbre propre"
assert git("push -q origin HEAD", work).returncode == 0

# ── Un conflit de code : rendu à l'utilisateur, jamais résolu d'office ──
work = repo({"frontend/app.js": b"// local", "site/data/rainfall.json": b"1"},
            {"frontend/app.js": b"// bot", "site/data/rainfall.json": b"2"})
r = git("pull --rebase --autostash", work, check=False)
assert r.returncode != 0
out = subprocess.run([str(RESOLVER)], cwd=work, capture_output=True, text=True)
assert out.returncode == 1, out.stdout
assert "frontend/app.js" in out.stdout and "à résoudre à la main" in out.stdout

print("OK — cartes de pluie et JSON de données résolus par .gitattributes, aucune macro « binary » "
      "n'annule la règle, filet de sécurité pour un fichier de données non déclaré, conflit de "
      "code rendu à l'utilisateur.")
