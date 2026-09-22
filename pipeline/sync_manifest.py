#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Met a jour les reglages d'appariement du site publie, sans reexport.

Le manifeste site/manifest.json embarque les reglages d'appariement —
decalage de datum, arrondi du niveau, poids — que le navigateur
applique pour choisir le scenario Delft3D. Il n'est ecrit que par
l'export complet, qui prend une a deux heures. Sans cette
synchronisation, un nouveau wlvl_offset ne changerait rien en ligne :
le serveur local et le site publie apparieraient des scenarios
differents, sans que rien ne le signale.

Seuls les blocs lies a config.yaml sont reecrits ; emprises, echelles
et couches restent intacts.

    python pipeline/sync_manifest.py
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from export_static import matching_config  # noqa: E402


def sync(cfg, manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    before = manifest.get("matching") or {}
    after = matching_config(cfg)
    label = (cfg.get("display") or {}).get("datum_label", "WSE (m)")

    changed = {k: (before.get(k), v) for k, v in after.items()
               if before.get(k) != v}
    if manifest.get("datum_label") != label:
        changed["datum_label"] = (manifest.get("datum_label"), label)

    manifest["matching"] = after
    manifest["datum_label"] = label
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return changed


def main():
    manifest_path = ROOT / "site" / "manifest.json"
    if not manifest_path.exists():
        print("site/manifest.json absent : lancez pipeline/export_static.py")
        return
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    changed = sync(cfg, manifest_path)
    if not changed:
        print("Manifeste : réglages d'appariement déjà à jour")
        return
    print("Manifeste : réglages d'appariement mis à jour")
    for key, (old, new) in changed.items():
        print(f"  {key} : {old} -> {new}")


if __name__ == "__main__":
    main()
