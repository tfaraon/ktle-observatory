#!/usr/bin/env bash
# Copie datee et compressee des fichiers de donnees du jour.
#
# Plusieurs jeux ne gardent qu'une fenetre glissante (meteo sur 7 jours,
# eBird et pluie sur 30 jours) : cette copie quotidienne en conserve
# l'historique sur le serveur, dans data/archive/AAAA/MM/JJ/.
# Environ quelques centaines de Ko par jour une fois compresses.
set -euo pipefail
cd "$(dirname "$0")/.."
day="$(date +%Y/%m/%d)"
dest="data/archive/$day"
mkdir -p "$dest"
for f in swot_wse.json weather.json lake_area.json water_extent.json \
         ebird.json inaturalist.json rainfall.json rivers.json; do
  [ -f "data/$f" ] && gzip -c "data/$f" > "$dest/$f.gz"
done
echo "Archive du jour : $dest ($(du -sh "$dest" | cut -f1))"
