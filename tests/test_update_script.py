#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Commande unique ./update.sh, executee pour de vrai dans un depot jetable.

Un depot Git et son depot distant sont crees en local ; deploy/refresh.sh
est remplace par une doublure qui note ses options, ecrit une donnee et,
sauf --no-publish, commit et pousse ; un petit serveur HTTP sert site/ et
joue le role de GitHub Pages.

Ce qui est verifie : l'aide ; l'arret sans rien publier quand des
fichiers modifies attendent et que personne ne confirme ; une
publication complete, verifiee en ligne ; le passage automatique en mode
rapide quand le disque SWOT n'est pas branche ; --no-push ; la lecture de
deploy/local.env ; les fichiers locaux ajoutes a .gitignore ; le journal.

Execution :  python tests/test_update_script.py
"""

import functools
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "update.sh"

STUB_REFRESH = """#!/usr/bin/env bash
echo "$@" > "$(dirname "$0")/../refresh_args.txt"
mkdir -p site/data && date +%s%N > site/data/x.json
case " $* " in *" --no-publish "*) exit 0 ;; esac
git add -A && git commit -qm "$2" && git push -q origin HEAD 2>/dev/null
"""


def sh(cmd, cwd, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, shell=True, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"{cmd}\n{r.stdout}\n{r.stderr}")
    return r


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    remote, work, stubs, swot = td / "remote.git", td / "work", td / "stubs", td / "swot"
    sh(f"git init -q --bare {remote}", td)
    sh(f"git clone -q {remote} {work}", td)
    stubs.mkdir(); (stubs / "netCDF4.py").write_text("")          # présence seulement
    swot.mkdir()
    (work / "deploy").mkdir()
    shutil.copy(SCRIPT, work / "update.sh")
    (work / "deploy" / "refresh.sh").write_text(STUB_REFRESH)
    os.chmod(work / "deploy" / "refresh.sh", 0o755)
    (work / "site" / "data").mkdir(parents=True)
    (work / "site" / "index.html").write_text("<p>site</p>")
    (work / "frontend").mkdir(); (work / "frontend" / "app.js").write_text("// v1\n")
    (work / "config.yaml").write_text(f"paths:\n  swot_data: {swot}\n")
    sh("git -c user.name=t -c user.email=t@t add -A && git -c user.name=t -c user.email=t@t "
       "commit -qm init && git push -q origin HEAD", work)
    sh("git config user.name t && git config user.email t@t", work)

    # « GitHub Pages » : un serveur qui sert site/
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(work / "site"))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"

    env = dict(os.environ, PYTHON=sys.executable, PYTHONPATH=str(stubs),
               DEPLOY_WAIT_TRIES="3", DEPLOY_WAIT_SECONDS="1")
    env.pop("EBIRD_API_KEY", None)
    (work / "deploy" / "local.env").write_text(f"SITE_URL={url}\nEBIRD_API_KEY=cle-test\n")
    remote_head = lambda: sh("git rev-parse HEAD", remote).stdout.strip()
    args = lambda: (work / "refresh_args.txt").read_text().split()

    # ── Aide ──
    r = sh("./update.sh --help", work, env)
    assert "./update.sh --quick" in r.stdout

    # ── Fichier modifié en attente, personne pour confirmer : rien n'est publié ──
    (work / "frontend" / "app.js").write_text("// v2\n")
    before = remote_head()
    r = sh("./update.sh < /dev/null", work, env, check=False)
    assert r.returncode == 1 and "frontend/app.js" in r.stdout and "-y" in r.stdout, r.stdout
    assert remote_head() == before, "rien ne doit partir"
    assert not (work / "refresh_args.txt").exists(), "aucun calcul lancé"

    # ── Publication complète, vérifiée en ligne ──
    r = sh("./update.sh -y < /dev/null", work, env, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "(en ligne)" in r.stdout, r.stdout
    assert remote_head() != before, "publié sur le dépôt distant"
    a = args()
    assert "--no-swot" not in a and "--no-publish" not in a and a[0] == "-m", a
    assert "EBIRD_API_KEY absente" not in r.stdout, "clé lue dans deploy/local.env"
    gi = (work / ".gitignore").read_text().split()
    assert "deploy/local.env" in gi and "logs/" in gi
    assert "local.env" not in sh("git ls-files", work).stdout, "réglages locaux jamais versionnés"
    logs = list((work / "logs").glob("update-*.log"))
    assert logs and "Mise à jour du site" in logs[0].read_text()

    # ── Disque SWOT débranché : mode rapide automatique ──
    swot.rmdir()
    r = sh("./update.sh -y < /dev/null", work, env, check=False)
    assert r.returncode == 0 and "disque non branché" in r.stdout, r.stdout
    assert "--no-swot" in args() and "--no-area" in args()

    # ── Calcul sans publication ──
    before = remote_head()
    r = sh("./update.sh --no-push < /dev/null", work, env, check=False)
    assert r.returncode == 0 and "--no-publish" in args() and remote_head() == before
    assert "Site    :" not in r.stdout
    # ── Dépôt injoignable : la cause est affichée, rien ne tourne ──
    sh(f"git remote set-url origin {td / 'absent.git'}", work)
    (work / "refresh_args.txt").unlink()
    r = sh("./update.sh -y < /dev/null", work, env, check=False)
    assert r.returncode == 1 and "Réponse de Git" in r.stdout and "absent.git" in r.stdout, r.stdout
    assert not (work / "refresh_args.txt").exists(), "aucun calcul lancé"
    srv.shutdown()

print("OK — aide, arrêt sans publier si personne ne confirme, publication vérifiée en ligne, "
      "mode rapide sans disque SWOT, --no-push, dépôt injoignable expliqué, réglages locaux lus "
      "et jamais versionnés, journal.")
