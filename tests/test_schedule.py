#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tache planifiee macOS (deploy/install_schedule.sh).

Une tache mal formee echoue en silence : launchd n'affiche rien et le
site cesse simplement de se rafraichir. Ce test lit donc le fichier
produit comme launchd le lirait, et verifie l'heure demandee, la
commande lancee, le repertoire de travail, le journal, et qu'aucune
saisie ne sera attendue (option -y).

Il verifie aussi l'installation dans un dossier jetable, sans toucher
au systeme.

Execution :  python tests/test_schedule.py
"""

import os
import plistlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "install_schedule.sh"


def run(args, env=None):
    return subprocess.run([str(SCRIPT)] + args, cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


# ── Contenu du fichier de tâche ──
r = run(["--print"])
assert r.returncode == 0, r.stderr
doc = plistlib.loads(r.stdout.encode("utf-8"))
assert doc["Label"] == "com.ktle.observatory.update"
assert doc["StartCalendarInterval"] == {"Hour": 9, "Minute": 15}
cmd = doc["ProgramArguments"][-1]
assert "./update.sh -y" in cmd, cmd
assert str(ROOT) in cmd and doc["WorkingDirectory"] == str(ROOT)
assert doc["StandardOutPath"].endswith("logs/schedule.log")
assert doc["RunAtLoad"] is False, "ne pas publier au simple chargement"
assert "/usr/bin" in doc["EnvironmentVariables"]["PATH"]

# ── Heure choisie ──
doc = plistlib.loads(run(["--print", "--hour", "6", "--minute", "5"]).stdout.encode("utf-8"))
assert doc["StartCalendarInterval"] == {"Hour": 6, "Minute": 5}

# ── Installation dans un dossier jetable ──
with tempfile.TemporaryDirectory() as td:
    r = run(["--hour", "7"], env={"LAUNCH_AGENTS": td})
    assert r.returncode == 0, r.stderr
    plist = Path(td) / "com.ktle.observatory.update.plist"
    assert plist.exists(), "fichier de tâche écrit"
    doc = plistlib.loads(plist.read_bytes())
    assert doc["StartCalendarInterval"]["Hour"] == 7
    assert "planifiée" in r.stdout or "launchctl load" in r.stdout

    r = run(["--uninstall"], env={"LAUNCH_AGENTS": td})
    assert r.returncode == 0 and not plist.exists(), "tâche retirée"
    assert "workflows GitHub continuent" in r.stdout

print("OK — fichier de tâche valide, heure réglable, commande sans saisie attendue, "
      "journal, installation et retrait sans toucher au système.")
