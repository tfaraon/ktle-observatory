# Déployer l'observatoire sur un serveur qui s'actualise seul

Ce guide installe le site sur une machine Linux toujours allumée. Le site y est
servi par Flask, derrière `nginx`, et ses données sont stockées localement dans
`data/`. Deux minuteurs `systemd` les mettent à jour sans intervention :

| Minuteur | Fréquence | Ce qu'il fait |
|---|---|---|
| `ktle-weather.timer` | toutes les heures | observations des stations BOM |
| `ktle-refresh.timer` | chaque jour à 7 h 30 | SWOT, surface et étendue d'eau, météo, eBird, iNaturalist, pluie SILO, rivières, puis copie datée des données |

Le serveur relit les fichiers de `data/` à chaque requête : une mise à jour est
visible immédiatement, sans redémarrage.

Les chemins supposent une installation dans `/srv/lake-eyre-dashboard`, avec un
utilisateur système `lakeeyre`. Si tu en choisis d'autres, modifie-les aussi
dans les fichiers de `deploy/systemd/` et dans `deploy/lake-eyre.service`.

## 1. La machine

- Linux (Ubuntu LTS par exemple), toujours allumée, avec un accès Internet
  sortant.
- 2 cœurs et 4 Go de mémoire suffisent.
- De la place pour `data/` (dont `compact.nc`, environ 280 Mo) et pour les
  granules SWOT. Mesure ces derniers sur le disque de Thomas avant de choisir :
  `du -sh /Volumes/tfaraon_PhD/Data/SWOT/download`.
- Pour une ouverture sur Internet : un nom de domaine et l'accord du service
  informatique de l'université. Sinon, le site peut rester accessible sur le
  seul réseau interne.

## 2. Installation

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin lakeeyre
sudo git clone https://github.com/tfaraon/ktle-observatory.git /srv/lake-eyre-dashboard
sudo chown -R lakeeyre:lakeeyre /srv/lake-eyre-dashboard
cd /srv/lake-eyre-dashboard
sudo -u lakeeyre python3 -m venv .venv
sudo -u lakeeyre .venv/bin/pip install -r requirements.txt gunicorn
```

## 3. Recopier les données depuis la machine de Thomas

Le serveur n'a besoin ni des 200 Go de sorties Delft3D ni du disque externe :
il lui faut le dossier `data/` et les granules SWOT déjà téléchargés. Sans ces
granules, le premier passage retéléchargerait tout depuis la date de départ
configurée (`download.start_date`, le 1er janvier 2025).

Depuis la machine de Thomas :

```bash
rsync -av --exclude rain_cache data/ serveur:/srv/lake-eyre-dashboard/data/
rsync -av /Volumes/tfaraon_PhD/Data/SWOT/download/ serveur:/srv/lake-eyre-dashboard/data/swot/
```

`data/` doit contenir au moins `compact.nc`, l'index des scénarios,
`bathymetry.npz` et `hypsometry.json`. Le cache de bathymétrie reste valide sur
le serveur : il est lié au nom du scénario, pas à un chemin. Remets ensuite les
droits : `sudo chown -R lakeeyre:lakeeyre /srv/lake-eyre-dashboard/data`.

## 4. Configuration

Dans `config.yaml`, fais pointer les deux chemins SWOT vers le serveur :

```yaml
paths:
  swot_data: "/srv/lake-eyre-dashboard/data/swot"
download:
  target_dir: "/srv/lake-eyre-dashboard/data/swot"
```

Les chemins `scenarios.directory` et `scenarios.design_csv` peuvent rester tels
quels : ils ne servent qu'à reconstruire les scénarios, ce qui se fait sur la
machine de Thomas.

Puis les secrets :

```bash
sudo cp deploy/ktle-observatory.env.example /etc/ktle-observatory.env
sudo nano /etc/ktle-observatory.env          # clé eBird, compte Earthdata
sudo chown root:lakeeyre /etc/ktle-observatory.env
sudo chmod 640 /etc/ktle-observatory.env
```

## 5. Un premier passage à la main

```bash
cd /srv/lake-eyre-dashboard
sudo -u lakeeyre bash -c 'set -a; . /etc/ktle-observatory.env; set +a;
  PYTHON=.venv/bin/python deploy/refresh.sh --no-publish'
```

Le bilan final liste les étapes réussies et celles en échec. C'est le moment
de corriger un chemin, un secret ou une dépendance, avant d'automatiser.

## 6. Le site web

```bash
sudo cp deploy/lake-eyre.service /etc/systemd/system/
sudo systemctl enable --now lake-eyre
sudo cp deploy/nginx.conf /etc/nginx/sites-available/lake-eyre
sudo ln -s /etc/nginx/sites-available/lake-eyre /etc/nginx/sites-enabled/
sudo nano /etc/nginx/sites-available/lake-eyre   # remplacer server_name
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ton-domaine              # HTTPS, si le site est public
```

Le bouton « Check for new data » reste désactivé (`LKE_ALLOW_REFRESH=0` dans le
service) : ce sont les minuteurs qui actualisent, pas les visiteurs.

## 7. L'actualisation automatique

```bash
sudo cp deploy/systemd/ktle-*.service deploy/systemd/ktle-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ktle-weather.timer ktle-refresh.timer
systemctl list-timers 'ktle-*'                   # prochains passages
journalctl -u ktle-refresh --since today         # journal du dernier passage
```

`Persistent=true` rattrape un passage manqué si la machine était éteinte.

## 8. Les données conservées

Après chaque passage quotidien, `deploy/archive.sh` range une copie compressée
de chaque fichier de données dans `data/archive/AAAA/MM/JJ/`. Plusieurs jeux ne
gardent qu'une fenêtre glissante (météo sur 7 jours, eBird et pluie sur 30
jours, rivières sur un an) : ces copies en conservent tout l'historique, pour
quelques centaines de Ko par jour.

Sauvegarde `data/` ailleurs, chaque nuit, par exemple vers un disque réseau :

```bash
# crontab de l'utilisateur lakeeyre
30 3 * * * rsync -a --delete --exclude .cache /srv/lake-eyre-dashboard/data/ /mnt/sauvegarde/ktle-data/
```

Les granules SWOT peuvent se retélécharger ; l'archive quotidienne, non.

## 9. Et GitHub Pages ?

Choisis une seule source de vérité. Si le serveur devient le site principal,
désactive les workflows planifiés de GitHub (Actions, puis *Disable workflow*)
pour ne pas interroger deux fois eBird et les autres services. Garder GitHub
Pages comme miroir reste possible : lance alors `deploy/refresh.sh` sans
`--no-publish` sur le serveur, avec une clé de déploiement SSH autorisée à
pousser sur le dépôt.

## En cas de problème

| Symptôme | Où regarder |
|---|---|
| Le site ne répond pas | `systemctl status lake-eyre`, `journalctl -u lake-eyre` |
| Les données ne bougent plus | `systemctl list-timers 'ktle-*'`, `journalctl -u ktle-refresh` |
| SWOT échoue | identifiants Earthdata dans `/etc/ktle-observatory.env` |
| eBird absent | `EBIRD_API_KEY` dans le même fichier |
| Erreur d'écriture | tout doit rester sous `data/`, seul répertoire accessible en écriture |
