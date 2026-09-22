#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coherence des fichiers de deploiement serveur (deploy/, deploy/systemd/).

Un serveur qui s'actualise seul ne pardonne pas une incoherence : un
chemin different d'un fichier a l'autre, un script absent ou un minuteur
qui ne declenche aucun service, et les donnees cessent de bouger sans
bruit. Ce test verifie que tous les services partagent le meme
repertoire, n'ecrivent que dans data/, lancent des scripts qui existent,
que chaque minuteur a son service, que le serveur ne publie pas, et
qu'aucun secret n'est versionne.

Execution :  python tests/test_deploy_units.py
"""

import configparser
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


def unit(path):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text(encoding="utf-8"))
    return cp


services = {p.name: unit(p) for p in sorted((DEPLOY / "systemd").glob("*.service"))}
services["lake-eyre.service"] = unit(DEPLOY / "lake-eyre.service")
timers = {p.name: unit(p) for p in sorted((DEPLOY / "systemd").glob("*.timer"))}
assert {"ktle-refresh.service", "ktle-weather.service"} <= set(services)
assert {"ktle-refresh.timer", "ktle-weather.timer"} == set(timers)

workdirs = {s["Service"]["WorkingDirectory"] for s in services.values()}
assert len(workdirs) == 1, f"répertoires différents : {workdirs}"
workdir = workdirs.pop()

for name, s in services.items():
    svc = s["Service"]
    assert svc.get("User") == "lakeeyre", name
    assert svc.get("ProtectSystem") == "strict", f"{name} : système en lecture seule"
    assert svc.get("ReadWritePaths") == f"{workdir}/data", f"{name} : écriture limitée à data/"
    # Le programme lancé existe dans le dépôt
    exe = svc["ExecStart"].replace("\\\n", " ").split()[0]
    if exe.startswith(workdir) and "/.venv/" not in exe:
        rel = Path(exe).relative_to(workdir)
        assert (ROOT / rel).exists(), f"{name} : {rel} absent"
    for arg in svc["ExecStart"].split()[1:]:
        if arg.startswith("pipeline/"):
            assert (ROOT / arg).exists(), f"{name} : {arg} absent"

# Chaque minuteur déclenche un service existant, et rattrape les passages manqués
for name, t in timers.items():
    assert name.replace(".timer", ".service") in services, name
    assert t["Timer"].get("Persistent") == "true", name
    assert "timers.target" in t["Install"]["WantedBy"], name

# Le passage quotidien met à jour sans publier, puis archive
refresh = services["ktle-refresh.service"]["Service"]
assert refresh["ExecStart"].endswith("refresh.sh --no-publish"), refresh["ExecStart"]
assert refresh["ExecStartPost"].endswith("deploy/archive.sh")
assert refresh["EnvironmentFile"] == "/etc/ktle-observatory.env"
for script in ("refresh.sh", "archive.sh"):
    mode = (DEPLOY / script).stat().st_mode
    assert mode & stat.S_IXUSR, f"{script} n'est pas exécutable"

# Modèle de secrets : les trois clés, aucune valeur
env = (DEPLOY / "ktle-observatory.env.example").read_text(encoding="utf-8")
keys = {}
for line in env.splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip()
assert set(keys) == {"EBIRD_API_KEY", "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"}, keys
assert all(v == "" for v in keys.values()), "le modèle ne doit contenir aucun secret"
assert not (DEPLOY / "ktle-observatory.env").exists(), "fichier de secrets versionné"

# Le guide renvoie aux bons fichiers
guide = (DEPLOY / "SERVEUR.md").read_text(encoding="utf-8")
for ref in ("ktle-refresh.timer", "ktle-weather.timer", "archive.sh", "--no-publish",
            "/etc/ktle-observatory.env", workdir):
    assert ref in guide, ref

print(f"OK — {len(services)} services dans {workdir}, écriture limitée à data/, scripts "
      f"présents, {len(timers)} minuteurs reliés à leurs services, aucune publication "
      "depuis le serveur, aucun secret versionné.")
