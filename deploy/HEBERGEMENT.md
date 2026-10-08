# Héberger le site hors de ta machine

Le site est déjà hébergé ailleurs : GitHub Pages le sert, et ton ordinateur
n'est pas dans le circuit quand quelqu'un l'ouvre. Ce qui dépend encore de ta
machine, c'est le **rafraîchissement** d'une partie des données — et seulement
d'une partie :

| Chaîne | Aujourd'hui | Pourquoi |
|---|---|---|
| Météo BOM | GitHub, chaque heure | aucune clé, aucune donnée locale |
| eBird, iNaturalist | GitHub, chaque jour | clé eBird en secret du dépôt |
| Pluie SILO, rivières | GitHub, chaque jour | sources publiques |
| **Niveaux SWOT** | ta machine | identifiants Earthdata, granules |
| **Surface en eau** | ta machine | lisait toute l'archive à chaque passage |
| **Étendue d'eau** | ta machine | a besoin de la bathymétrie du modèle |

La question est donc : où faire tourner ces trois dernières chaînes. Trois
voies, de la plus légère à la plus lourde.

---

## A. Tout dans GitHub Actions — recommandé

Aucune machine à gérer, aucun abonnement, et le site continue de se mettre à
jour même si ton ordinateur reste éteint un mois.

Ce qui rendait cela impossible jusqu'ici : `lake_area.py` relisait les 761
granules à chaque passage, donc l'archive devait rester montée. Les deux
chaînes sont maintenant incrémentales et gardent leur mémoire dans `state/` :

- `state/extraction_cache.json` — niveaux déjà extraits, par granule ;
- `state/area_cache.json` — surface déjà calculée, par **journée** (la surface
  se calcule sur la grille fusionnée du jour, c'est la seule unité
  réutilisable).

Un granule peut donc être téléchargé, lu, puis jeté. `.github/workflows/swot.yml`
fait exactement cela : il télécharge les nouveaux granules dans le dossier
temporaire du runner, calcule, publie, et le runner disparaît avec les fichiers.

Conséquence à connaître : les deux séries sont désormais reconstruites depuis
le cache, non depuis les granules présents. Retirer un granule de l'archive ne
le retire donc plus de la série ; c'est `--rebuild-cache` qui le fait. Et comme
un cache perdu produit un passage *réussi* sur une poignée de granules plutôt
qu'une erreur, `tools/check_series.py` compare chaque série publiée à celle déjà
en ligne et refuse de publier la plus courte. `ALLOW_SHORTER=1` passe outre,
pour le jour où une série doit légitimement raccourcir.

### Mise en route, une seule fois

1. **Secrets du dépôt** — *Settings → Secrets and variables → Actions* :
   `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` (compte urs.earthdata.nasa.gov).
   La clé `EBIRD_API_KEY` y est déjà.

2. **Verser l'état et la bathymétrie**, depuis ta machine, archive montée.
   Le cache de surface n'existe pas encore : c'est le premier passage avec le
   nouveau code qui l'écrit, en traitant les 420 granules une dernière fois.
   Il suffit donc de lui dire où le ranger, puis de lancer un passage normal,
   qui le publiera lui-même :

   ```bash
   echo 'KTLE_STATE_DIR=state' >> deploy/local.env
   ./update.sh                      # écrit state/*.json et les publie
   ls -lh state/ data/bathymetry.npz
   git add -f data/bathymetry.npz && git commit -m "Bathymétrie" && git push
   ```

   `state/extraction_cache.json` et `state/area_cache.json` doivent tous deux
   s'y trouver à la fin, le second avec une centaine de journées.

   `data/bathymetry.npz` vient de `compact.nc`, qui n'est pas dans le dépôt :
   sans lui, le workflow saute l'étendue d'eau et ne fait que les niveaux et la
   surface. S'il dépasse 100 Mo, GitHub le refusera — dans ce cas, garde
   l'étendue en local, ou passe ce seul fichier par Git LFS.

3. **Essayer à la main** : *Actions → Refresh SWOT levels and lake area → Run
   workflow*, puis lire le journal. Le workflow refuse de tourner si `state/`
   manque, pour ne jamais publier une série reconstruite sur les seuls granules
   du jour.

4. **Ta machine devient facultative** : `./deploy/install_schedule.sh --uninstall`
   retire la tâche quotidienne. `./update.sh` reste utilisable quand tu veux
   un passage complet, et le pilote de fusion `keepnew` fait que les deux ne se
   gênent pas.

### Ce que ça coûte, ce que ça casse

- Gratuit : les workflows d'un dépôt public ne consomment pas de quota.
- Un workflow planifié est **désactivé après 60 jours sans activité dans le
  dépôt**. Les commits quotidiens des autres chaînes suffisent à l'éviter.
- Le dépôt grossit d'un commit par jour et par chaîne. Les cartes PNG pèsent
  le plus ; `deploy/archive.sh` et un `git gc` annuel suffisent pour l'instant.
- Les runners sont en Amérique du Nord : le BOM et Water Data Online peuvent
  refuser leurs adresses. C'est déjà le cas aujourd'hui et les chaînes
  concernées conservent alors les données précédentes — à surveiller dans
  l'onglet Actions.
- Un historique de 420 journées dépend de `state/area_cache.json`. Il est
  versionné, donc récupérable, mais ne le supprime pas sans avoir l'archive
  sous la main pour reconstruire (`--rebuild-cache`).

---

## B. Une petite machine Linux allumée en permanence

`deploy/SERVEUR.md` l'installe déjà : Flask derrière nginx, données dans
`data/`, deux minuteurs systemd. À choisir si tu veux :

- l'API Flask vivante (téléchargements à la demande, scénarios Delft3D) et pas
  seulement l'export statique ;
- garder les données hors de GitHub ;
- un nom de domaine à toi, avec un certificat que tu contrôles.

En pratique : un VPS à 5–10 €/mois (Hetzner, Scaleway, OVH), ou une machine de
l'université si le service informatique l'accepte. L'ancien portable sous Linux
Mint fait l'affaire techniquement, mais chez toi il dépend de ta connexion et
de ton électricité ; pour un site public, un VPS est plus tranquille.

Coût réel : ce n'est pas l'argent, c'est l'entretien — mises à jour de
sécurité, certificat, sauvegardes, et une panne qui ne prévient pas. Pour un
site consulté de temps en temps, la voie A demande moins d'attention.

---

## C. Mixte : l'archive dans le nuage

Si un jour il faut reconstruire la série complète sans le disque de Thomas,
copie l'archive SWOT dans un stockage objet (S3, R2, B2 — quelques euros par
mois pour quelques centaines de gigaoctets) et monte-la sur le serveur de la
voie B, ou télécharge à la demande. `KTLE_SWOT_DIR` suffit à pointer ailleurs,
sans toucher à `config.yaml` :

```bash
KTLE_SWOT_DIR=/mnt/swot python pipeline/lake_area.py --rebuild-cache
```

À ne faire que pour ce besoin-là. Au quotidien, le cache de la voie A rend
l'archive inutile.

---

## Et le nom de domaine

Indépendant de tout ce qui précède. Sur GitHub Pages : ajouter le domaine dans
*Settings → Pages*, créer un `CNAME` chez le registraire, cocher *Enforce
HTTPS*. Le certificat est automatique. Un passage ultérieur vers la voie B ne
change que l'adresse IP du DNS.

## Variables d'environnement

| Variable | Rôle | Par défaut |
|---|---|---|
| `KTLE_SWOT_DIR` | où lire et télécharger les granules | `paths.swot_data` de `config.yaml` |
| `KTLE_STATE_DIR` | où ranger les caches des chaînes | `data/` |
| `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` | téléchargement SWOT | `~/.netrc` |
| `EBIRD_API_KEY` | observations eBird | — |

Les deux premières existent pour que `config.yaml`, qui est versionné, n'ait
pas à être modifié sur chaque machine : le modifier ferait un conflit à chaque
publication.
