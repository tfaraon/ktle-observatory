#!/usr/bin/env bash
#
# Planifie la mise a jour quotidienne du site sur ce Mac.
#
#   ./deploy/install_schedule.sh                 # tous les jours a 9 h
#   ./deploy/install_schedule.sh --hour 7        # a une autre heure
#   ./deploy/install_schedule.sh --status        # etat de la tache
#   ./deploy/install_schedule.sh --run           # lancer tout de suite
#   ./deploy/install_schedule.sh --uninstall
#
# La tache appelle ./update.sh -y : elle calcule, publie et verifie que la
# mise a jour est en ligne. Sans le disque SWOT branche, update.sh saute
# SWOT et la surface en eau et met a jour le reste.
#
# Ce qui se passe deja sans cette tache : les workflows GitHub rafraichissent
# la meteo toutes les heures, puis eBird, iNaturalist, la pluie et les
# rivieres chaque jour. La tache locale ajoute ce qui a besoin du disque.
#
# Prealable, une seule fois, pour que la publication n'attende aucune saisie :
#   ssh-add --apple-use-keychain ~/.ssh/id_ed25519
# et, dans ~/.ssh/config :
#   Host github.com
#     AddKeysToAgent yes
#     UseKeychain yes
#     IdentityFile ~/.ssh/id_ed25519
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LABEL="com.ktle.observatory.update"
PLIST_DIR="${LAUNCH_AGENTS:-$HOME/Library/LaunchAgents}"
PLIST="$PLIST_DIR/$LABEL.plist"
HOUR=9
MINUTE=15
ACTION="install"

while [ $# -gt 0 ]; do
  case "$1" in
    --hour) shift; HOUR="${1:-9}" ;;
    --minute) shift; MINUTE="${1:-15}" ;;
    --status) ACTION="status" ;;
    --run) ACTION="run" ;;
    --uninstall) ACTION="uninstall" ;;
    --print) ACTION="print" ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 2 ;;
  esac
  shift
done

plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd '$ROOT' &amp;&amp; ./update.sh -y</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>StandardOutPath</key><string>$ROOT/logs/schedule.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/schedule.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF
}

case "$ACTION" in
  print)
    plist ;;
  status)
    if launchctl list | grep -q "$LABEL"; then
      echo "Tâche active :"
      launchctl list "$LABEL" | sed -n '1,12p'
    else
      echo "Aucune tâche installée. Pour l'installer : ./deploy/install_schedule.sh"
    fi
    [ -f "$ROOT/logs/schedule.log" ] && echo && tail -5 "$ROOT/logs/schedule.log" ;;
  run)
    launchctl start "$LABEL" && echo "Lancée. Suivre avec :  tail -f logs/schedule.log" ;;
  uninstall)
    launchctl unload "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "Tâche retirée. Les workflows GitHub continuent de tourner." ;;
  install)
    mkdir -p "$PLIST_DIR" "$ROOT/logs"
    plist > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null
    if launchctl load "$PLIST" 2>/dev/null; then
      printf 'Mise à jour planifiée chaque jour à %02d h %02d.\n' "$HOUR" "$MINUTE"
    else
      printf 'Fichier écrit dans %s ; le charger avec :\n    launchctl load %s\n' "$PLIST" "$PLIST"
    fi
    echo "Journal : logs/schedule.log ; état : ./deploy/install_schedule.sh --status"
    echo "Si le Mac dort à cette heure, la tâche part à son réveil." ;;
esac
