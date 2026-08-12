#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Premier lancement : enchaine toutes les etapes puis demarre le site.

    python startup.py

Etapes, dans l'ordre :
  1. verification de la configuration et des chemins ;
  2. telechargement et extraction SWOT   -> data/swot_wse.json
  3. observations meteo BOM              -> data/weather.json
  4. index des scenarios Delft3D         -> data/scenarios.json
  5. compactage des sorties              -> data/compact.nc
  6. demarrage du serveur.

Chaque etape est ignoree si son resultat existe deja : relancer la
commande ne refait que ce qui manque. Les etapes 2 et 5 peuvent durer
des heures au premier lancement ; les suivantes sont rapides.

Options utiles :
    --skip-download    n'interroge pas la NASA (extraction seule)
    --skip-compact     saute le compactage (le site lit alors les
                       NetCDF d'origine, plus lent mais fonctionnel)
    --layers 0,9       couches conservees au compactage
    --force            refait les etapes meme si le resultat existe
    --no-serve         s'arrete avant de demarrer le serveur
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

OK, SKIP, WARN, FAIL = "ok", "skip", "warn", "fail"
MARK = {OK: "✓", SKIP: "·", WARN: "!", FAIL: "✗"}


def human(seconds):
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def run(cmd, label):
    """Lance une etape en laissant sa sortie s'afficher en direct."""
    print(f"\n── {label} " + "─" * max(0, 58 - len(label)))
    print(f"   {' '.join(cmd[1:])}\n")
    t0 = time.time()
    code = subprocess.call(cmd, cwd=str(ROOT))
    return code, time.time() - t0


def check_config(cfg_path):
    """Controles prealables : ce qui manque ici coute des heures plus tard."""
    import yaml

    problems, notes = [], []
    if not cfg_path.exists():
        return [f"config.yaml introuvable ({cfg_path})"], []

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    swot = Path(str((cfg.get("paths") or {}).get("swot_data", ""))).expanduser()
    if not swot.exists():
        notes.append(f"répertoire SWOT absent ({swot}) — il sera créé au "
                     "téléchargement")

    scen = (cfg.get("scenarios") or {}).get("directory")
    if not scen:
        problems.append("scenarios.directory non renseigné")
    elif not Path(str(scen)).expanduser().exists():
        problems.append(f"répertoire des simulations introuvable ({scen}) — "
                        "le disque externe est-il monté ?")

    design = (cfg.get("scenarios") or {}).get("design_csv")
    if design and not Path(str(design)).expanduser().exists():
        notes.append(f"plan d'expérience introuvable ({design}) — la "
                     "comparaison au plan sera ignorée")

    if not (cfg.get("sites") or []):
        problems.append("aucun site d'extraction dans config.yaml")

    return problems, notes


def main():
    parser = argparse.ArgumentParser(
        description="Premier lancement de l'observatoire",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-swot", action="store_true",
                        help="Saute entièrement l'étape SWOT")
    parser.add_argument("--skip-weather", action="store_true")
    parser.add_argument("--skip-compact", action="store_true")
    parser.add_argument("--layers", default="0,9",
                        help="Couches conservées au compactage (défaut 0,9 "
                             "= première et dixième)")
    parser.add_argument("--force", action="store_true",
                        help="Refait chaque étape même si le résultat existe")
    parser.add_argument("--no-serve", action="store_true")
    args = parser.parse_args()

    py = sys.executable
    cfg_path = Path(args.config)

    print("=" * 64)
    print("  Observatoire Kati Thanda – Lake Eyre — premier lancement")
    print("=" * 64)

    problems, notes = check_config(cfg_path)
    for n in notes:
        print(f"  {MARK[WARN]} {n}")
    if problems:
        print("\nConfiguration incomplète :")
        for p in problems:
            print(f"  {MARK[FAIL]} {p}")
        print("\nCorrigez config.yaml puis relancez.")
        return 1
    print(f"  {MARK[OK]} configuration lue ({cfg_path.name})")

    report = []

    # ── 1. SWOT ──────────────────────────────────────────────
    swot_json = DATA / "swot_wse.json"
    if args.skip_swot:
        report.append((SKIP, "SWOT", "ignoré (--skip-swot)"))
    elif swot_json.exists() and not args.force:
        report.append((SKIP, "SWOT", f"{swot_json.name} existe déjà"))
    else:
        cmd = [py, "pipeline/update_swot.py", "--config", str(cfg_path)]
        if not args.skip_download:
            cmd.append("--download")
            print("\nLe téléchargement SWOT peut durer longtemps au premier "
                  "lancement.\nIdentifiants Earthdata demandés une seule "
                  "fois, puis mémorisés dans ~/.netrc.")
        code, dt = run(cmd, "1/5  Niveaux d'eau SWOT")
        report.append((OK if code == 0 else FAIL, "SWOT",
                       f"{human(dt)}" if code == 0
                       else f"échec (code {code})"))
        if code != 0:
            print("\n  Le site fonctionnera sans les niveaux d'eau, mais "
                  "l'appariement des scénarios en dépend.")

    # ── 2. Meteo ─────────────────────────────────────────────
    if args.skip_weather:
        report.append((SKIP, "Météo", "ignorée (--skip-weather)"))
    else:
        code, dt = run([py, "pipeline/fetch_weather.py",
                        "--config", str(cfg_path)], "2/5  Observations BOM")
        # Une panne du BOM ne doit pas bloquer le demarrage
        report.append((OK if code == 0 else WARN, "Météo",
                       human(dt) if code == 0 else "BOM injoignable"))

    # ── 3. Index des scenarios ───────────────────────────────
    index_json = DATA / "scenarios.json"
    need_index = args.force or not index_json.exists()
    if not need_index:
        try:
            import json
            with open(index_json, "r", encoding="utf-8") as f:
                need_index = bool(json.load(f).get("demo"))
            if need_index:
                print("\n  Index de démonstration détecté : reconstruction.")
        except Exception:
            need_index = True
    if need_index:
        code, dt = run([py, "pipeline/scenario_index.py",
                        "--config", str(cfg_path)], "3/5  Index des scénarios")
        report.append((OK if code == 0 else FAIL, "Index", human(dt)
                       if code == 0 else f"échec (code {code})"))
        if code != 0:
            print("\nSans index, aucun scénario ne peut être affiché. Arrêt.")
            return 1
    else:
        report.append((SKIP, "Index", f"{index_json.name} existe déjà"))

    # ── 4. Compactage ────────────────────────────────────────
    compact_nc = DATA / "compact.nc"
    if args.skip_compact:
        report.append((SKIP, "Compactage", "ignoré (--skip-compact)"))
    elif compact_nc.exists() and not args.force:
        report.append((SKIP, "Compactage", f"{compact_nc.name} existe déjà"))
    else:
        cmd = [py, "pipeline/compact.py", "--config", str(cfg_path),
               "--layers", args.layers]
        if compact_nc.exists():
            cmd.append("--resume")
        print("\nLe compactage lit les 790 simulations : comptez une à "
              "plusieurs heures.\nIl est interruptible : relancer la "
              "commande reprend où elle s'est arrêtée.")
        code, dt = run(cmd, "4/5  Compactage des sorties Delft3D")
        report.append((OK if code == 0 else WARN, "Compactage",
                       human(dt) if code == 0
                       else "échec — le site lira les NetCDF d'origine"))

    # ── Bilan ────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  Bilan")
    print("=" * 64)
    for status, label, detail in report:
        print(f"  {MARK[status]} {label:<12} {detail}")

    if any(st == FAIL for st, _, _ in report):
        print("\nUne étape essentielle a échoué : corrigez avant de servir "
              "le site.")
        return 1

    if args.no_serve:
        print("\nPrêt. Démarrez le site avec :  python run.py")
        return 0

    print("\n── 5/5  Démarrage du serveur " + "─" * 34)
    print("   http://127.0.0.1:8000     (Ctrl+C pour arrêter)\n")
    try:
        return subprocess.call([py, "run.py"], cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\nServeur arrêté.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
