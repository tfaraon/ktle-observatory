#!/usr/bin/env bash
#
# Met a jour les donnees et publie le site, en une commande.
#
#   ./update.sh                 # tout : SWOT, surface, etendue, meteo, eBird,
#                               # iNaturalist, pluie, rivieres ; publie ; verifie
#   ./update.sh --quick         # sans SWOT ni surface (quelques minutes)
#   ./update.sh --no-push       # calcule sans publier
#   ./update.sh -y              # sans confirmation
#   ./update.sh -m "message"    # message de commit
#
# Reglages locaux (cle eBird, environnement Python, adresse du site) :
# deploy/local.env, a creer depuis deploy/local.env.example. Ce fichier
# n'est jamais versionne.
#
# Le script verifie d'abord ce qui ferait echouer une longue execution
# (Python, disque SWOT, acces au depot), lance deploy/refresh.sh, puis
# attend que GitHub Pages serve bien la nouvelle version. Le journal
# complet est garde dans logs/.
#
# Compatible avec le bash 3.2 de macOS.
set -uo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

QUICK=0; PUSH=1; YES=0; MESSAGE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=1 ;;
    --no-push) PUSH=0 ;;
    -y|--yes) YES=1 ;;
    -m) shift; MESSAGE="${1:-}" ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1  (./update.sh --help)"; exit 2 ;;
  esac
  shift
done

# ── Reglages locaux ─────────────────────────────────────────
if [ -f deploy/local.env ]; then
  set -a; . deploy/local.env; set +a
fi
SITE_URL="${SITE_URL:-https://tfaraon.github.io/ktle-observatory/}"
SITE_URL="${SITE_URL%/}/"

# Fichiers locaux jamais versionnes
touch .gitignore
for pattern in "deploy/local.env" "logs/"; do
  grep -qxF "$pattern" .gitignore || echo "$pattern" >> .gitignore
done

# ── Journal ─────────────────────────────────────────────────
mkdir -p logs
LOG="logs/update-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
START=$(date +%s)
echo "Mise à jour du site, $(date '+%d/%m/%Y %H:%M')"
echo

fail() { echo; echo "Arrêt : $1"; echo "Journal : $LOG"; exit 1; }
warn() { echo "  attention : $1"; }

# ── Python ──────────────────────────────────────────────────
if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif [ -n "${CONDA_ENV:-}" ] && command -v conda >/dev/null 2>&1; then
  PY="$(conda run -n "$CONDA_ENV" python -c 'import sys; print(sys.executable)' 2>/dev/null | tail -1)"
  [ -n "$PY" ] || fail "environnement conda « $CONDA_ENV » introuvable"
else
  PY="$(command -v python3 || command -v python || true)"
fi
[ -n "$PY" ] || fail "aucun Python trouvé (réglez PYTHON ou CONDA_ENV dans deploy/local.env)"
"$PY" -c "import numpy, yaml, netCDF4, PIL" 2>/dev/null \
  || fail "il manque des bibliothèques à $PY (numpy, PyYAML, netCDF4, Pillow)"
echo "Python : $PY"
"$PY" -c "import earthaccess" 2>/dev/null || warn "earthaccess absent : pas de téléchargement SWOT"

# ── Disque SWOT ─────────────────────────────────────────────
SWOT_DIR="$("$PY" -c "import yaml; print(yaml.safe_load(open('config.yaml'))['paths']['swot_data'])" 2>/dev/null)"
if [ "$QUICK" -eq 0 ] && [ ! -d "$SWOT_DIR" ]; then
  warn "dossier SWOT introuvable ($SWOT_DIR) : disque non branché ?"
  warn "SWOT et surface en eau sont sautés, le reste est mis à jour"
  QUICK=1
fi

# ── Clés ────────────────────────────────────────────────────
[ -n "${EBIRD_API_KEY:-}" ] || warn "EBIRD_API_KEY absente : eBird sera sauté"

# ── Depot : acces et modifications en attente ───────────────
[ -d .git ] || fail "pas de dépôt Git dans $ROOT"
if [ "$PUSH" -eq 1 ]; then
  # La cle SSH est chargee maintenant, au besoin : sinon sa phrase secrete
  # est demandee en plein travail, et une publication peut echouer dix
  # minutes apres le debut du calcul.
  case "$(git remote get-url origin 2>/dev/null)" in
    *git@*|ssh://*)
      if [ -t 0 ] && ! ssh-add -l >/dev/null 2>&1; then
        for k in "${SSH_KEY:-}" ~/.ssh/id_ed25519 ~/.ssh/id_rsa; do
          [ -n "$k" ] && [ -f "$k" ] || continue
          echo "Chargement de la clé SSH ($k) : la phrase secrète n'est demandée qu'une fois."
          ssh-add --apple-use-keychain "$k" 2>/dev/null || ssh-add -K "$k" 2>/dev/null || ssh-add "$k" || true
          break
        done
      fi ;;
  esac
  # Au terminal, ssh peut demander la phrase secrete de la cle ; sans
  # terminal (tache planifiee), il ne doit jamais attendre de reponse.
  SSH_OPTS="-o ConnectTimeout=10"
  [ -t 0 ] || SSH_OPTS="$SSH_OPTS -o BatchMode=yes"
  if ! GIT_ERR="$(GIT_SSH_COMMAND="ssh $SSH_OPTS" git ls-remote --heads origin 2>&1 >/dev/null)"; then
    echo
    echo "Dépôt : $(git remote get-url origin 2>/dev/null || echo 'aucun remote « origin »')"
    echo "Réponse de Git :"
    echo "$GIT_ERR" | tail -4 | sed 's/^/    /'
    case "$GIT_ERR" in
      *"Permission denied"*)
        echo "Piste : cette machine n'a pas de clé SSH reconnue par GitHub, ou pas d'accès au dépôt." ;;
      *"timed out"*|*"Connection refused"*|*"Could not resolve"*)
        echo "Piste : le réseau bloque SSH (port 22) ; passer par le port 443, voir README." ;;
      *"Host key verification failed"*)
        echo "Piste : lancer une fois « ssh -T git@github.com » et accepter la clé de GitHub." ;;
      *"passphrase"*|*"agent"*)
        echo "Piste : la clé SSH a une phrase secrète non chargée : « ssh-add --apple-use-keychain »." ;;
    esac
    fail "le dépôt GitHub ne répond pas"
  fi
  # Tout ce qui est modifie hors des donnees sera publie avec elles
  PENDING="$(git status --porcelain | grep -v ' site/data/' | grep -v ' logs/' | grep -v '\.gitignore$' || true)"
  if [ -n "$PENDING" ]; then
    echo
    echo "Ces fichiers modifiés seront publiés avec les données :"
    echo "$PENDING" | head -20 | sed 's/^/    /'
    if [ "$YES" -eq 0 ]; then
      if [ -t 0 ]; then
        printf "Continuer ? [o/N] "
        read -r answer
        case "$answer" in o|O|oui|y|Y|yes) ;; *) fail "annulé, rien n'a été publié" ;; esac
      else
        fail "modifications en attente ; relancer avec -y pour les publier"
      fi
    fi
  fi
fi

# ── Mise a jour et publication ──────────────────────────────
ARGS=""
[ "$QUICK" -eq 1 ] && ARGS="$ARGS --no-swot --no-area"
[ "$PUSH" -eq 0 ] && ARGS="$ARGS --no-publish"
[ -n "$MESSAGE" ] || MESSAGE="Data refresh $(date '+%Y-%m-%d %H:%M')"

STAMP=""
if [ "$PUSH" -eq 1 ] && [ -d site/data ]; then
  # Marque de cette publication, pour verifier ensuite qu'elle est en ligne
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  printf '{"published_at": "%s", "stamp": "%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$STAMP" > site/data/build.json
fi

echo
HEAD_BEFORE="$(git rev-parse HEAD)"
# shellcheck disable=SC2086
PYTHON="$PY" ./deploy/refresh.sh $ARGS -m "$MESSAGE"
STATUS=$?

# ── Poussee : un commit deja pret n'est pas abandonne ───────
upstream() { git rev-parse '@{u}' 2>/dev/null || echo "-"; }
if [ "$PUSH" -eq 1 ] && [ "$(git rev-parse HEAD)" != "$HEAD_BEFORE" ] \
   && [ "$(git rev-parse HEAD)" != "$(upstream)" ]; then
  echo
  echo "Les données sont enregistrées mais pas encore envoyées. Nouvel essai de publication…"
  if git push; then
    STATUS=0
  else
    echo
    echo "La poussée a encore échoué. Rien n'est perdu : le commit est prêt en local."
    echo "Charge ta clé puis pousse-la :"
    echo "    ssh-add --apple-use-keychain ~/.ssh/id_ed25519"
    echo "    git push"
    STATUS=1
  fi
fi

# ── Verification en ligne ───────────────────────────────────
ONLINE="non vérifié"
if [ "$PUSH" -eq 1 ] && [ -n "$STAMP" ] \
   && [ "$(git rev-parse HEAD)" != "$HEAD_BEFORE" ] \
   && [ "$(git rev-parse HEAD)" = "$(git rev-parse '@{u}' 2>/dev/null)" ]; then
  echo
  echo "Publié. Attente du déploiement de GitHub Pages (jusqu'à 10 minutes)…"
  WAIT="${DEPLOY_WAIT_TRIES:-30}"; PAUSE="${DEPLOY_WAIT_SECONDS:-20}"
  ONLINE="pas encore visible"
  i=0
  while [ "$i" -lt "$WAIT" ]; do
    if curl -fsS --max-time 15 "${SITE_URL}data/build.json?nocache=$(date +%s)" 2>/dev/null \
         | grep -q "$STAMP"; then
      ONLINE="en ligne"
      break
    fi
    i=$((i + 1))
    [ "$i" -lt "$WAIT" ] && sleep "$PAUSE"
  done
elif [ "$PUSH" -eq 1 ] && [ -n "$STAMP" ]; then
  ONLINE="rien de publié"
fi

# ── Bilan ───────────────────────────────────────────────────
ELAPSED=$(( $(date +%s) - START ))
echo
echo "────────────────────────────────────────"
echo "Durée   : $((ELAPSED / 60)) min $((ELAPSED % 60)) s"
[ "$STATUS" -eq 0 ] && echo "Étapes  : toutes réussies" || echo "Étapes  : au moins une en échec (voir plus haut)"
if [ "$PUSH" -eq 1 ]; then
  echo "Site    : $SITE_URL ($ONLINE)"
  [ "$ONLINE" = "pas encore visible" ] && \
    echo "          le déploiement prend du temps : voir l'onglet Actions du dépôt"
fi
echo "Journal : $LOG"
exit "$STATUS"
