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
# Images du site (aperçu de partage, figures des pages) et leur manifeste
if [ -d frontend/img ]; then
  mkdir -p site/img
  cp -R frontend/img/. site/img/ 2>/dev/null || true
fi
cp -f frontend/figures.json site/ 2>/dev/null || true
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
for name in swot_wse.json weather.json lake_area.json water_extent.json ebird.json inaturalist.json rainfall.json rivers.json; do
  if [ -f "data/$name" ]; then
    if ! cmp -s "data/$name" "site/data/$name"; then
      cp "data/$name" "site/data/"
      data_copied=$((data_copied + 1))
    fi
  fi
done
echo "Données  : $data_copied fichier(s) mis à jour"

# Masques d'eau SWOT : un PNG par date
for folder in area_maps extent_maps rain_maps; do
  [ -d "data/$folder" ] || continue
  mkdir -p "site/data/$folder"
  if ! diff -rq "data/$folder" "site/data/$folder" >/dev/null 2>&1; then
    cp "data/$folder"/*.png "site/data/$folder/" 2>/dev/null || true
    echo "Masques $folder : $(ls -1 "site/data/$folder"/*.png 2>/dev/null | wc -l | tr -d ' ') date(s)"
  fi
done

# Reglages d'appariement du site : decalage de datum, arrondi du niveau.
# Le manifeste n'est ecrit que par l'export complet ; sans cette etape,
# un nouveau wlvl_offset resterait sans effet en ligne.
if [ -f site/manifest.json ]; then
  python3 pipeline/sync_manifest.py || echo "Attention : manifeste non synchronisé"
fi

# Rappel : les images du modele ne sont regenerees que par l'export.
if [ ! -d site/img ] || [ -z "$(ls -A site/img 2>/dev/null)" ]; then
  echo "Attention : site/img est vide — les couches du modèle ne"
  echo "            s'afficheront pas. Lancez pipeline/export_static.py"
fi

# ── Commit ──────────────────────────────────────────────────
# Le pilote « ours » de .gitattributes doit etre declare une fois par
# depot ; sans lui, Git ignore la regle et le conflit revient.
# Le resolveur est mis a l'abri : pendant un rebase, l'arbre de travail
# est celui du commit rejoue, ou ce fichier peut ne pas exister encore.
RESOLVER="$(mktemp -t ktle-resolve)"
cp deploy/resolve_conflicts.sh "$RESOLVER" 2>/dev/null && chmod +x "$RESOLVER"
trap 'rm -f "$RESOLVER"' EXIT

# Donnees regenerables : on garde la version calculee par ce passage
# plutot que de fusionner. Pendant un rebase, %B est le commit rejoue.
git config --get merge.keepnew.driver >/dev/null 2>&1 || \
  git config merge.keepnew.driver 'cp -f %B %A'

# Garde-fou : une serie plus courte que celle deja publiee signale un
# cache incremental ignore, pas une donnee qui aurait disparu. Le calcul
# reussit dans les deux cas, d'ou ce controle avant tout commit.
if [ "${ALLOW_SHORTER:-0}" != "1" ]; then
  if ! python3 tools/check_series.py site/data/swot_wse.json \
        site/data/lake_area.json site/data/water_extent.json; then
    echo
    echo "Pour publier malgré tout : ALLOW_SHORTER=1 ./update.sh"
    exit 1
  fi
fi

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
if ! git pull --rebase --autostash; then
  # Conflit de donnees entre cette machine et le workflow GitHub : la
  # version calculee ici est gardee, le reste revient a l'utilisateur.
  "$RESOLVER" || {
    echo "Publication interrompue : dépôt laissé en l'état pour inspection."
    exit 1
  }
fi
git push
echo
echo "Publié. Le workflow « Deploy site » démarre si site/ a changé."
