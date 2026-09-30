#!/usr/bin/env bash
#
# Termine un rebase bloque par un conflit portant uniquement sur les
# donnees (site/data). Appele par publish.sh quand « git pull --rebase »
# echoue.
#
# Les fichiers de data/ sont recalcules a chaque passage : quand la
# machine locale et le workflow GitHub produisent chacun leur version du
# meme jour, il n'y a rien a fusionner. On garde alors la version qui
# vient d'etre calculee ici, c'est a dire celle du commit rejoue
# (« theirs » pendant un rebase), et on poursuit.
#
# Un conflit ailleurs que dans site/data touche du code ou du texte : il
# est rendu a l'utilisateur, jamais resolu d'office.
set -uo pipefail
# On agit sur le depot d'ou l'on est appele, pas sur celui du script
top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$top" ] && cd "$top"

conflicted="$(git diff --name-only --diff-filter=U)"
if [ -z "$conflicted" ]; then
  echo "Aucun conflit à résoudre."
  exit 0
fi

outside="$(printf '%s\n' "$conflicted" | grep -v '^site/data/' || true)"
if [ -n "$outside" ]; then
  echo "Conflit hors des données, à résoudre à la main :"
  printf '%s\n' "$outside" | sed 's/^/    /'
  exit 1
fi

echo "Conflit sur les données seules : la version calculée ici est conservée."
printf '%s\n' "$conflicted" | while IFS= read -r f; do
  [ -n "$f" ] || continue
  git checkout --theirs -- "$f" 2>/dev/null || git checkout --ours -- "$f" 2>/dev/null || true
  git add -- "$f"
  echo "    $f"
done

if GIT_EDITOR=true git rebase --continue; then
  exit 0
fi
echo "Le rebase n'a pas pu se terminer."
exit 1
