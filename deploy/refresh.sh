#!/usr/bin/env bash
#
# Rafraichit les donnees puis publie.
#
#   ./deploy/refresh.sh                  # SWOT + meteo + surface, puis publie
#   ./deploy/refresh.sh --no-swot        # sans telechargement SWOT (rapide)
#   ./deploy/refresh.sh --only-area      # surface seule, puis publie
#   ./deploy/refresh.sh --no-publish     # calcule sans publier
#   ./deploy/refresh.sh -m "message"
#
# Chaque etape est independante : une meteo injoignable n'empeche pas de
# publier une nouvelle serie SWOT. La publication n'a lieu que si au
# moins une etape a reussi, et le code de sortie reflete les echecs —
# de quoi etre averti si le script tourne sans surveillance.

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

DO_SWOT=1; DO_WEATHER=1; DO_AREA=1; DO_PUBLISH=1
MESSAGE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-swot) DO_SWOT=0 ;;
    --no-weather) DO_WEATHER=0 ;;
    --no-area) DO_AREA=0 ;;
    --no-publish) DO_PUBLISH=0 ;;
    --only-area) DO_SWOT=0; DO_WEATHER=0 ;;
    -m) shift; MESSAGE="${1:-}" ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 2 ;;
  esac
  shift
done

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
FAILED=0
CHANGED=0

run_step() {          # run_step "libelle" commande...
  local label="$1"; shift
  echo "── $(stamp)  $label"
  if "$@"; then
    echo "   OK"
    CHANGED=1
  else
    echo "   ÉCHEC (code $?)"
    FAILED=$((FAILED + 1))
  fi
}

echo "=== Rafraîchissement de l'observatoire — $(stamp) ==="

if [ "$DO_SWOT" -eq 1 ]; then
  # --download exige des identifiants Earthdata deja memorises dans
  # ~/.netrc : lancez-le une fois en terminal avant toute planification.
  run_step "Niveaux d'eau SWOT" "$PY" pipeline/update_swot.py --download
fi

[ "$DO_WEATHER" -eq 1 ] && run_step "Observations BOM" "$PY" pipeline/fetch_weather.py

[ "$DO_AREA" -eq 1 ] && run_step "Surface en eau" "$PY" pipeline/lake_area.py

echo
if [ "$CHANGED" -eq 0 ]; then
  echo "Aucune étape n'a abouti : rien à publier."
  exit 1
fi

if [ "$DO_PUBLISH" -eq 1 ]; then
  [ -n "$MESSAGE" ] || MESSAGE="Data refresh $(date +%Y-%m-%d)"
  echo "── $(stamp)  Publication"
  if ./deploy/publish.sh "$MESSAGE"; then
    echo "   OK"
  else
    echo "   ÉCHEC de la publication"
    FAILED=$((FAILED + 1))
  fi
else
  echo "Publication ignorée (--no-publish)."
fi

echo
if [ "$FAILED" -gt 0 ]; then
  echo "Terminé avec $FAILED échec(s) — $(stamp)"
  exit 1
fi
echo "Terminé sans erreur — $(stamp)"
