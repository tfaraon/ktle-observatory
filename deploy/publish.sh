#!/usr/bin/env bash
#
# Publie les mises a jour du site.
#
#   ./deploy/publish.sh "message de commit"
#   ./deploy/publish.sh -n                  # prepare sans pousser
#
# Le pipeline ecrit dans data/, que .gitignore exclut deliberement — les
# granules et le fichier compact n'ont rien a faire dans le depot. Le
# site publie lit sa propre copie sous site/data/ : ce script fait donc
# la recopie, puis le commit. C'est l'etape qu'on oublie, et le site
# reste alors fige sans que rien ne le signale.

set -euo pipefail

PUSH=1
MESSAGE=""
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--no-push) PUSH=0 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) MESSAGE="$1" ;;
  esac
  shift
done

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# ── Verifications ───────────────────────────────────────────
[ -d .git ] || { echo "Erreur : pas de dépôt Git dans $ROOT"; exit 1; }
[ -d site ] || { echo "Erreur : site/ absent — lancez pipeline/export_static.py"; exit 1; }
if [ -d site/.git ]; then
  echo "Erreur : site/.git existe. Git traiterait site/ comme un sous-module"
  echo "         et ne publierait aucun fichier.  rm -rf site/.git"
  exit 1
fi

# ── Frontend ────────────────────────────────────────────────
# Copie de TOUS les fichiers, sans liste en dur : un nouveau module
# oublie (methods.js, windrose.js, download.js...) laisserait le site
# en ligne partiellement casse.
copied=0
for f in frontend/*.html frontend/*.css frontend/*.js; do
  [ -e "$f" ] || continue
  if ! cmp -s "$f" "site/$(basename "$f")"; then
    cp "$f" site/
    copied=$((copied + 1))
  fi
done
echo "Frontend : $copied fichier(s) mis à jour"

# ── Donnees ─────────────────────────────────────────────────
mkdir -p site/data
data_copied=0
for name in swot_wse.json weather.json lake_area.json; do
  if [ -f "data/$name" ]; then
    if ! cmp -s "data/$name" "site/data/$name"; then
      cp "data/$name" "site/data/"
      data_copied=$((data_copied + 1))
    fi
  fi
done
echo "Données  : $data_copied fichier(s) mis à jour"

# Masques d'eau SWOT : un PNG par date
if [ -d data/area_maps ]; then
  mkdir -p site/data/area_maps
  if ! diff -rq data/area_maps site/data/area_maps >/dev/null 2>&1; then
    cp data/area_maps/*.png site/data/area_maps/ 2>/dev/null || true
    echo "Masques : $(ls -1 site/data/area_maps/*.png 2>/dev/null | wc -l | tr -d ' ') date(s)"
  fi
fi

# Rappel : les images du modele ne sont regenerees que par l'export.
if [ ! -d site/img ] || [ -z "$(ls -A site/img 2>/dev/null)" ]; then
  echo "Attention : site/img est vide — les couches du modèle ne"
  echo "            s'afficheront pas. Lancez pipeline/export_static.py"
fi

# ── Commit ──────────────────────────────────────────────────
# Le pilote « ours » de .gitattributes doit etre declare une fois par
# depot ; sans lui, Git ignore la regle et le conflit revient.
git config --get merge.ours.driver >/dev/null 2>&1 || \
  git config merge.ours.driver true

git add -A
if git diff --cached --quiet; then
  echo "Rien à publier : le dépôt est déjà à jour."
  exit 0
fi

echo
echo "Fichiers concernés :"
git diff --cached --stat | tail -12

[ -n "$MESSAGE" ] || MESSAGE="Update site ($(date +%Y-%m-%d))"
git commit -q -m "$MESSAGE"
echo "Commit : $MESSAGE"

if [ "$PUSH" -eq 0 ]; then
  echo "Poussée ignorée (--no-push). Terminez avec :  git push"
  exit 0
fi

# Le workflow météo pousse sur main toutes les heures : on rejoue
# par-dessus plutot que d'echouer sur un rejet.
git pull --rebase --autostash
git push
echo
echo "Publié. Le workflow « Deploy site » démarre si site/ a changé."
