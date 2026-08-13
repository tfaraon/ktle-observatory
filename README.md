# Observatoire Kati Thanda – Lake Eyre

Interface web pour visualiser l'état du lac : niveau d'eau observé par
SWOT (dernière observation + série temporelle), en attendant l'ajout des
résultats du modèle Delft3D-FLOW / SWAN.

L'architecture sépare le **calcul** (pipeline Python, exécuté à la
demande) de l'**affichage** (site statique servi par Flask) : le site
lit un unique fichier `data/swot_wse.json` régénéré par le pipeline.

```
lake-eyre-dashboard/
├── SWOT_toolbox/          # ta toolbox, intégrée telle quelle (voir note)
├── pipeline/
│   ├── update_swot.py     # extraction SWOT -> data/swot_wse.json
│   ├── fetch_weather.py   # observations BOM -> data/weather.json
│   ├── scenarios.py       # parsing des noms + appariement
│   ├── scenario_index.py  # index des simulations -> data/scenarios.json
│   ├── scenario_field.py  # lecture d'un champ 2D (+ --inspect)
│   ├── geo.py             # reprojection MGA <-> WGS84
│   ├── check_runs.py      # contrôle de l'archive (runs incomplets)
│   ├── compact.py         # compactage -> data/compact.nc
│   ├── compact_store.py   # lecture du fichier compact
│   └── export_static.py   # site statique pré-calculé -> site/
├── backend/
│   └── app.py             # serveur Flask : frontend + API
├── frontend/              # index.html, style.css, app.js
├── data/                  # swot_wse.json, weather.json, scenarios.json
├── tests/                 # test_pipeline_wiring, test_incremental, test_weather
├── config.yaml            # sites, filtres, chemins
├── requirements.txt
├── run.py                 # lance le serveur
└── startup.py             # premier lancement : toutes les étapes
```

L'interface du site est en anglais ; la documentation et les
commentaires du code restent en français.

## Démarrage rapide

```bash
pip install -r requirements.txt
python startup.py
```

`startup.py` enchaîne toutes les étapes d'un premier lancement :
vérification de la configuration, téléchargement et extraction SWOT,
observations BOM, index des scénarios, compactage, puis démarrage du
serveur. Chaque étape est **ignorée si son résultat existe déjà**, donc
relancer la commande ne refait que ce qui manque.

Les contrôles préalables valent le détour : ils vérifient que le disque
des simulations est monté et que les chemins de `config.yaml` existent,
avant de lancer des heures de traitement. Un index de démonstration
laissé en place est détecté et reconstruit automatiquement.

| Option | Effet |
|---|---|
| `--skip-download` | extraction SWOT seule, sans interroger la NASA |
| `--skip-compact` | pas de compactage (le site lit alors les NetCDF d'origine) |
| `--layers 0,9` | couches conservées au compactage (défaut : 1 et 10) |
| `--force` | refait chaque étape même si le résultat existe |
| `--no-serve` | prépare tout sans démarrer le serveur |

Comptez plusieurs heures au premier lancement (téléchargement SWOT et
compactage) ; les suivants sont immédiats. Les deux étapes longues sont
interruptibles et reprennent où elles s'étaient arrêtées.

Les sections suivantes détaillent chaque étape, pour les lancer
séparément ou comprendre ce qu'elles font.

## Installation

```bash
pip install -r requirements.txt
```

## 1. Configurer

Ouvrir `config.yaml` :

- `paths.swot_data` : répertoire des granules NetCDF SWOT (parcouru
  récursivement) — par défaut le disque `tfaraon_PhD`.
- `sites` : points d'extraction. Deux sites sont actifs — **Belt Bay**
  (137,028 °E ; point bas du lac) et **Madigan Gulf** (137,560 °E). Le
  transect ouest de `SWOT_WSE_work.py` est en commentaire, prêt à être
  activé. `scenarios.wlvl_site` désigne celui qui fournit le niveau
  d'eau pour l'appariement des scénarios.
- `extraction` : reprend les paramètres du notebook (`buffer_size=6`,
  `wse_qual_filter=[0,1,2]`, outliers IQR, bornes [-16, 6] m, fenêtre
  depuis 2025-01-01).
- `datum_offset` (par site) : valeur **ajoutée** à la WSE affichée,
  utile pour passer du géoïde EGM2008 à un repère local (0.0 = valeur
  SWOT brute).

## 2. Récupérer les dernières données et générer le JSON

```bash
python pipeline/update_swot.py --download # nouveaux granules + extraction
python pipeline/update_swot.py            # extraction seule (fichiers en place)
python pipeline/update_swot.py --demo     # données synthétiques (aperçu)
```

Tout est **incrémental**, donc rapide à répéter :

- **Recherche** : la fenêtre earthaccess couvre [dernier granule local
  − `lookback_days` ; aujourd'hui] (la marge rattrape les granules
  livrés en retard). Premier lancement sur répertoire vide :
  `download.start_date`. Seuls les fichiers absents du disque sont
  téléchargés.
- **Extraction** : chaque fichier n'est traité qu'une fois par site
  (cache `data/extraction_cache.json`, worker `_process_file` de ta
  toolbox) ; les filtres bornes [-16, 6] puis outliers IQR sont ensuite
  ré-appliqués sur la série complète, à l'identique de
  `extract_wse_timeseries_parallel`. Changer `buffer_size` ou
  `wse_qual_filter` invalide le cache du site automatiquement.

Drapeaux utiles : `--rebuild-cache` (retraite tout),
`--no-cache` (appelle la fonction d'origine de la toolbox — vérification
croisée : le résultat doit être identique).

**Identifiants Earthdata** : lancer une première fois `--download` dans
un terminal ; `earthaccess.login(persist=True)` les demande puis les
mémorise dans `~/.netrc`. Ensuite, tout est non-interactif (bouton du
site, cron). Aucun identifiant n'est stocké dans ce dépôt.

**Depuis le site** : le bouton « Rechercher les nouvelles données »
(visible quand la page est servie par Flask) lance
téléchargement + extraction en arrière-plan et recharge la page à la
fin. À noter : les granules Raster arrivent avec quelques jours de
latence après l'acquisition.

**Automatisation** (mise à jour quotidienne à 7 h, par exemple) :

```cron
0 7 * * * cd /chemin/vers/lake-eyre-dashboard && /usr/bin/env python3 pipeline/update_swot.py --download >> data/update.log 2>&1
```

### Versions de collection (C → D)

Depuis le **3 mai 2025**, la collection Version C
(`SWOT_L2_HR_Raster_2.0`) est figée côté PO.DAAC : les acquisitions
suivantes — et le retraitement homogène de tout l'historique — sont
publiées dans **`SWOT_L2_HR_Raster_D`**. La config interroge donc la
Version D par défaut (`download.short_names`), la Version C restant en
commentaire pour l'accès à l'archive historique.

Conséquence pour la série : mélanger des granules C (avant mai 2025) et
D (après) introduit un changement de chaîne de traitement au milieu de
la série. Acceptable pour le tableau de bord ; pour les articles, le
plus propre est de re-synchroniser tout l'historique en Version D :

```bash
# 1. mettre l'archive C de côté
mv /Volumes/.../SWOT/download /Volumes/.../SWOT/download_versionC
# 2. ajuster download.start_date si besoin, puis :
python pipeline/update_swot.py --download --rebuild-cache
```

Après chaque mise à jour, le message « À jour — dernier granule
distant : … » permet de vérifier d'un coup d'œil que la recherche voit
bien des granules récents côté PO.DAAC ; « Aucun granule trouvé sur la
fenêtre » signale au contraire un problème de collection ou de motifs.

Le mode `--demo` produit une série synthétique clairement étiquetée
(bandeau orange sur le site) pour prévisualiser l'interface sans
données.

## 3. Météo BOM et imagerie satellite

### Observations BOM

Le site affiche les dernières observations (vent, rafales, température,
humidité, pression, pluie depuis 9 h) des stations listées dans
`config.yaml` → `weather.stations`. Par défaut : Marree Airport,
Oodnadatta et Moomba Airport, qui encadrent le lac.

La récupération passe **par le serveur** : le pare-feu applicatif du BOM
rejette les requêtes sans en-tête `User-Agent` de navigateur, et le
navigateur ne peut de toute façon pas interroger bom.gov.au directement
(pas d'en-tête CORS). Flask sert donc `/api/weather`, avec un cache de
`weather.cache_minutes` (15 min par défaut) pour rester courtois envers
le BOM — les stations ne publient qu'un relevé toutes les 10–30 min.

```bash
python pipeline/fetch_weather.py          # récupère et écrit data/weather.json
python pipeline/fetch_weather.py --demo   # observations synthétiques
```

**Roses des vents.** Le volet météo affiche une rose par station, avec
un sélecteur de période : *All, 7 days, 7 nights, 24 h, Last day, Last
night*. Le partage jour/nuit repose sur l'**élévation solaire réelle**
au lac (calculée dans `frontend/windrose.js`), et non sur des heures
fixes : il s'agit de séparer la couche limite diurne, bien mélangée, de
la couche nocturne découplée. Les périodes *Last day* et *Last night*
retiennent la dernière plage continue de la phase demandée, donc une
vraie journée ou une vraie nuit.

La logique est testée sous Node (`node tests/test_windrose.js`) :
élévation solaire vérifiée contre la géométrie (46,2° au midi solaire
du 12 août à 28,9 °S), durées de jour aux solstices, saisonnalité
inversée dans l'hémisphère nord, sélection des périodes et répartition
directionnelle.

**Archive de 7 jours.** Le BOM ne publie qu'une fenêtre glissante de 72 h.
À chaque récupération, les relevés déjà connus sont fusionnés avec le
flux courant (dédoublonnage par horodatage), ce qui maintient une
archive continue de `weather.history_hours` (168 h par défaut) même si
le flux est tronqué ou si une récupération échoue. Au-delà des 72 h
publiées par le Bureau, l'archive se construit donc progressivement, au
rythme des exécutions du cron. Le vent des trois stations est tracé sous
les cartes de conditions.

Robustesse : si une station devient injoignable, sa **dernière
observation valide est conservée** et signalée « relevé conservé » en
ocre, plutôt qu'effacée — une coupure BOM ne vide pas le tableau de
bord. Pour ajouter une station, ouvrir sa page « Latest Weather
Observations » sur bom.gov.au et relever le produit (`IDS60801` en
Australie-Méridionale, `IDQ60801` dans le Queensland) et le numéro WMO
depuis le lien JSON en bas de page.

### Imagerie MODIS / VIIRS

La barre au-dessus de la carte bascule entre le fond topographique et
les couches d'imagerie servies par **NASA GIBS** (projection EPSG:3857),
définies dans `config.yaml` → `imagery.layers`. Par défaut :

| Bouton | Couche GIBS |
|---|---|
| MODIS 7-2-1 | `MODIS_Terra_CorrectedReflectance_Bands721` |
| MODIS couleur | `MODIS_Terra_CorrectedReflectance_TrueColor` |
| VIIRS 7-2-1 | `VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1` |

Ajouter ou remplacer une couche = ajouter une entrée `{ label, layer }`
à la liste, puis recharger la page (aucune modification de JavaScript,
`/api/config` transmet la liste au frontend). Le catalogue complet des
identifiants est sur
<https://nasa-gibs.github.io/gibs-api-docs/available-visualizations/>.

**Pourquoi 7-2-1 par défaut** : la bande 7 (SWIR, 2,1 µm) est fortement
absorbée par l'eau, qui ressort donc en bleu très sombre, alors que la
croûte de sel et les sols nus restent clairs. Le contour de la nappe est
bien plus net qu'en vraies couleurs, où une eau peu profonde et chargée
se confond facilement avec le sel — utile pour comparer l'extension
observée aux cellules mouillées du modèle.

Par défaut, la date vaut `default` : GIBS renvoie alors l'image la plus
récente disponible — typiquement celle du jour même, quelques heures
après le passage. Les flèches ◀ ▶ et le sélecteur de date permettent de
remonter dans le temps, par exemple pour comparer une image à une
observation SWOT donnée ; « Dernière » revient à l'image courante.

Deux limites à connaître : la résolution native MODIS plafonne à 250 m
(le zoom au-delà du niveau 9 étire les tuiles), et une image très
récente peut être partiellement vide si la tuile n'a pas encore été
produite — reculer d'un jour suffit alors.

## 4. Lancer le site

```bash
python run.py
```

Puis ouvrir <http://127.0.0.1:8000>. Après une nouvelle exécution du
pipeline, il suffit de recharger la page (le JSON est relu à chaque
requête).

API : `/api/wse` (payload complet), `/api/wse/latest` (dernière
observation par site), `/api/weather` (observations BOM, cache TTL),
`/api/config` (couches d'imagerie), `/api/scenarios`,
`/api/scenario/match` (paramètre `at` pour un instant passé),
`/api/scenario/field`, `/api/scenario/currents`,
`/api/health`, `POST /api/refresh` (pipeline en arrière-plan ;
`?download=0` pour extraction seule) et `/api/refresh/status`.

## 5. Scénarios Delft3D

Le dernier volet apparie les **conditions observées** (vent BOM +
niveau SWOT) au **scénario pré-calculé le plus proche**, puis trace le
champ correspondant.

### Indexation

```bash
python pipeline/scenario_index.py          # indexe scenarios.directory
python pipeline/scenario_index.py --list   # affiche la grille indexée
python pipeline/scenario_index.py --demo   # index synthétique (aperçu)
```

L'index ne lit que les **noms de fichiers**, et regroupe les deux
sorties d'un même run :

```
Output/Wave/wave_wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc
Output/Flow/     wind-sp1_0_wind-dir0_0_wlvl-7_0_sal250_0.nc
                      └ 1.0 m/s  └ 0.0°   └ -7.0 m  └ 250.0 g/L
```

Le séparateur décimal est un **underscore** (`wind-sp12_5` = 12,5 m/s),
et le tiret de `wlvl-7_0` est lu comme le **signe** (−7,0 m). Si cette
dernière convention est fausse, `scenarios.wlvl_sign: "positive"`
l'inverse. La sortie WAVE est reconnue par son préfixe `wave_`, la
FLOW par son dossier ; un run dont une seule sortie existe reste
utilisable.

Si `scenarios.design_csv` pointe vers `lhs_all.csv`, l'indexation
compare le plan d'expérience aux fichiers présents et liste les runs
**prévus mais manquants** — pratique pour repérer les simulations qui
ont échoué.

**Fichiers parasites macOS.** Copier depuis macOS vers un volume
exFAT/FAT (disque externe, partage réseau) crée à côté de chaque
fichier un jumeau `._nom.nc` : ce sont des métadonnées AppleDouble, pas
des NetCDF. Comme `.` précède les lettres, ils passaient devant les
vrais fichiers et provoquaient une erreur *Unknown file format*.
L'indexation les écarte désormais, ainsi que `__MACOSX` et les dossiers
cachés, et vérifie l'en-tête de chaque fichier (`verify_format: true`)
pour éliminer aussi les sorties tronquées. Le nombre de fichiers
ignorés est affiché à la fin de l'indexation. Pour les supprimer du
disque :

```bash
dot_clean -m /Volumes/.../Output      # macOS
find /chemin/Output -name '._*' -delete
```

### Appariement

Le plan est un tirage LHS : 800 lignes pour 26 880 combinaisons
possibles, soit environ 3 % de l'espace. Le voisin le plus proche est
donc souvent à distance non négligeable sur plusieurs axes à la fois,
et c'est un arbitrage, pas une correspondance.

La distance est normalisée par l'**étendue** de chaque paramètre
(`normalize: "range"`, adapté à un plan lacunaire ; `"step"` convient à
une grille factorielle régulière), la direction du vent étant traitée
circulairement sur 180° — 350° tombe sur 0°, pas sur 315°. Les
`weights` arbitrent quel paramètre sacrifier : vent et direction
pilotent la génération des vagues, la salinité n'agit que par la masse
volumique, d'où des poids de 1,0 / 1,0 / 0,8 / 0,3 par défaut.

Le site affiche pour chaque paramètre la valeur observée, celle du
scénario retenu et l'écart ; un paramètre hors de la plage simulée
passe en ocre avec un avertissement explicite. Seul le scénario le plus
proche est affiché ; les suivants restent disponibles dans le champ
`alternatives` de `/api/scenario/match`.

Trois conversions, toutes explicites dans `config.yaml` :

| Réglage | Rôle |
|---|---|
| `wind_station` | station BOM fournissant le vent (km/h → m/s automatique) |
| `wind_dir_convention` | `from` (nautique, comme le BOM) ou `to` (vectorielle) |
| `wlvl_offset` | décalage ajouté à la WSE SWOT pour rejoindre le datum du modèle |

### Remonter le temps

Une frise sous l'en-tête du volet parcourt l'archive météo de 48 h :
curseur, bouton *Now*, et lecture automatique. À chaque position, les
conditions de l'instant choisi sont réappariées et le champ affiché
suit.

Une distinction vaut d'être gardée en tête, car elle diffère d'un site
comme Alplakes : chaque simulation est un **état stationnaire séparé**,
pas une série temporelle. Remonter à 24 h ne fait pas défiler le temps
*dans* un modèle, cela change **quel scénario** correspond aux
conditions d'alors. La date SWOT retenue est la dernière observation
antérieure à l'instant demandé — les passes étant espacées d'une
dizaine de jours, le niveau reste en général constant sur 48 h et c'est
le vent qui pilote le changement de scénario.

Exploration manuelle :
`/api/scenario/match?wind_speed=25&wind_dir=270&wlvl=-11`, ou
`/api/scenario/match?at=2026-08-10T03:00:00Z` pour un instant donné.

### Tracé du champ

Un sélecteur bascule entre la sortie **Vagues** (WAVE) et
**Hydrodynamique** (FLOW), chacune proposant ses propres champs.

```bash
python pipeline/scenario_field.py --inspect chemin/vers/fichier.nc
```

liste les variables, leurs dimensions, leur point de calcul
(`face`, `edge1`…) et les réductions qui seront appliquées. Les noms
détectés dans les fichiers fournis :

| Sortie | Champs (noms confirmés par `--inspect`) |
|---|---|
| WAVE | `hsign` (Hs), `setup`, `period`, `dir`, `wlength`, `depth` — coordonnées `x`, `y`, grille (280, 207), 5 pas de temps |
| FLOW | `S1` (niveau, *face*), `U1`/`V1` (*edge1*/*edge2*, 10 couches), `TAUKSI`/`TAUETA`/`TAUMAX`, `RHO` (10 couches), `R1` (1 constituant × 10 couches) — coordonnées `XZ`, `YZ`, grille (208, 281), 24 pas de temps |

`XCOR`/`YCOR` sont écartés de la liste : ce sont les coins de mailles,
pas des champs physiques.

Le champ ouvert par défaut est `hsign` pour une sortie WAVE et `S1`
pour une sortie FLOW ; l'ordre de priorité est défini par
`PRIORITY_NAMES` dans `scenario_field.py`.

**Couches du modèle sur la carte.** Comme sur Alplakes, les sorties
Delft3D se superposent au fond de carte plutôt que d'occuper un
graphique séparé. Quatre couches, choisies dans la barre au-dessus de
la carte :

| Couche | Source | Champ | Flèches |
|---|---|---|---|
| Currents | FLOW | vitesse `√(U1²+V1²)` | courant, longueur ∝ vitesse |
| Wave height | WAVE | `hsign` | direction des vagues |
| Wavelength | WAVE | `wlength` | direction des vagues |
| Period | WAVE | `period` | direction des vagues |

La construction du champ suit `map_data_quiver` : intensité interpolée
linéairement, valeurs sous 1e-6 rendues transparentes, lissage gaussien
insensible aux NaN (`current_smooth`), palette turbo, flèches blanches.
**Le masque du domaine en eau est explicite**, et c'est essentiel : le
déduire de « valeur non nulle » confondrait un lac **calme** (courants
nuls, mais en eau) avec un lac **sec**, et la couche apparaîtrait vide
sur tous les scénarios à vent faible. Le masque vient donc d'une
grandeur qui ne s'annule qu'hors de l'eau — le niveau `S1` côté FLOW,
la profondeur `depth` côté WAVE. Dans le fichier compact, les mailles
sèches sont stockées en valeur de remplissage, ce qui les distingue
d'une valeur nulle légitime.

Une subtilité en découle : le masque est évalué au **plus proche
voisin** (défini partout), alors que la grandeur affichée vient d'une
interpolation **linéaire** (indéfinie hors de l'enveloppe convexe des
points). Là où le lac touche le bord du domaine, une flèche peut donc
être retenue à un endroit où l'intensité vaut NaN. Le serveur écarte
ces points et refuse par ailleurs d'émettre du JSON non conforme
(`allow_nan=False`) : une valeur non finie provoque une erreur tracée
côté serveur plutôt qu'une réponse que le navigateur rejette en bloc.

Les mailles sèches restent **dans** le jeu d'interpolation : ce sont
elles qui tirent le champ vers zéro au bord du lac. Un tirage au plus
proche voisin sur le masque sert ensuite de porte — un point n'est
coloré, et une flèche n'est tracée, que si la maille de modèle la plus
proche est en eau. C'est ce qui donne un trait de côte net là où
l'interpolation linéaire laisserait une traînée.

La longueur des flèches est exprimée en **pixels écran** et recalculée
à chaque zoom, sinon une longueur géographique enflerait dès qu'on
s'approche. Le curseur *Arrows* de la barre de carte la règle
(`arrow_px` par défaut : 16 px).

**Reprojection.** Le modèle travaille en mètres projetés (MGA), Leaflet
en degrés. Le serveur ré-échantillonne donc chaque champ directement
sur une grille lon/lat régulière — l'image se pose alors sans
déformation sur la carte. La conversion inverse est implémentée dans
`pipeline/geo.py` (séries de Snyder, ellipsoïde GRS80) plutôt que via
pyproj : pas de dépendance supplémentaire, et un aller-retour vérifié
au dixième de millimètre. Le fuseau est déduit de la position du lac
(137,5 °E → zone 53) ; `scenarios.utm_zone` permet de le forcer, et le
serveur signale explicitement si le domaine reprojeté ne retombe pas
sur le lac — une erreur de fuseau déplacerait tout de plusieurs degrés
sans autre symptôme.

Deux corrections d'orientation, invisibles mais réelles :

- **Courants** : `U1`/`V1` sont exprimés dans le repère de la grille
  (ksi, eta). La rotation vers x/y est estimée par le gradient des
  coordonnées, puis la **convergence des méridiens** (≈ 1,2° à Kati
  Thanda) ramène l'azimut de grille à un azimut vrai.
- **Vagues** : `dir` suit la convention nautique de SWAN — direction
  d'où viennent les vagues. Les flèches montrent la propagation, donc
  +180°. `wave_dir_convention: "to"` inverse ce choix.

Les bornes de couleur sont fixées par couche (`layer_scales`) afin que
l'échelle ne saute pas d'un scénario à l'autre en parcourant la frise.

**Valeurs nulles.****Valeurs nulles.** Dans les cellules sèches, Delft3D écrit 0 plutôt
qu'une valeur manquante ; conservé, ce zéro écrase la dynamique du
champ. `mask_zero: "auto"` les masque pour `U1`, `V1`, `TAUKSI`,
`TAUETA` et `TAUMAX` ; `true` les masque partout, `false` nulle part.

Quatre points traités automatiquement :

- **Lecture partielle** : les sorties FLOW pèsent plusieurs centaines
  de Mo ; seule la tranche demandée est lue, jamais la variable
  entière.
- **Dimensions supplémentaires** : `time`, `KMAXOUT_RESTR` (couches) et
  `LSTSCI` (constituants) sont réduites par indice, **indépendamment**
  les unes des autres. Les valeurs de départ viennent de `time_index`
  et `layer_index`, mais des sélecteurs *couche k/10* et *pas k/24*
  apparaissent au-dessus du graphique dès qu'une variable porte ces
  dimensions.

  **Quelle couche est la surface ?** Delft3D numérote habituellement
  depuis la surface (indice 0 = couche supérieure), mais cela dépend de
  la configuration. Le plus simple est de vérifier sur le modèle
  lui-même : afficher `RHO` et comparer la couche 1 à la couche 10 —
  dans un lac hypersalin la masse volumique doit croître vers le fond.
  Un contrôle équivalent avec `U1` sous vent fort : la vitesse de
  surface doit dépasser celle du fond.
- **Grille décalée** : `U1`, `V1`, `TAUKSI` et `TAUETA` sont calculés
  aux faces (`edge1`/`edge2`), pas aux centres de mailles. Comme leurs
  tableaux ont la même forme que `XZ`/`YZ`, ils sont tracés aux centres
  avec un décalage d'une demi-maille — sans conséquence visuelle à
  cette échelle, et signalé sous le graphique. Si les formes ne
  correspondaient pas, le tracé basculerait sur les indices de maille
  plutôt que d'échouer.
- **Grille régulière stockée en 2D** : si `XZ`/`YZ` décrivent en fait
  une grille régulière, les axes en sont déduits directement — la
  résolution native est conservée et la triangulation de plusieurs
  dizaines de milliers de points évitée. L'interpolation ne sert que
  pour les grilles réellement curvilignes ; la mention apparaît sous le
  graphique.
- **Cellules hors domaine** : Delft3D n'y écrit pas un masque mais des
  sentinelles — `0` et `-999.999` côté FLOW, la valeur de remplissage
  NetCDF (~9,97e36) côté WAVE. Conservées, elles étirent l'emprise du
  tracé jusqu'à l'origine et écrasent le lac dans un coin. Elles sont
  écartées des coordonnées comme du champ, et le nombre de cellules
  actives est affiché sous le graphique. Le `0` n'est traité comme
  sentinelle que si les coordonnées sont clairement projetées : le test
  porte sur le **maximum** des valeurs (un degré ne dépasse pas 360),
  et non sur leur médiane, qui vaut 0 dès que la majorité des cellules
  sont inactives.
- **Coordonnées de repli** : si `XZ`/`YZ` sont absentes, vides ou
  dégénérées, le lecteur bascule sur `XCOR`/`YCOR` (coins de mailles).
- **Coordonnées projetées** : les axes sont en mètres
  (`projected_coordinate_system`), pas en degrés ; le rapport d'aspect
  est conservé. C'est aussi pourquoi le champ n'est pas encore
  superposable à la carte Leaflet — il faudrait la reprojection.

## Schéma du JSON (swot_wse.json)

```json
{
  "generated_at": "2026-08-10T02:00:00Z",
  "demo": false,
  "lake": { "name": "...", "center": {...}, "zoom": 8 },
  "datum_label": "WSE (m, géoïde EGM2008)",
  "source": { "n_granules": 214, "last_granule_date": "2026-07-28T03:12:45",
              "new_this_run": 4, "downloaded": 4, "found_in_window": 12,
              "last_remote_granule_date": "2026-08-05T03:10:12" },
  "sites": [
    {
      "name": "Belt Bay", "lon": 137.028098, "lat": -28.893022,
      "datum_offset": 0.0,
      "latest": { "date": "2026-07-28T03:12:45", "wse": -12.31 },
      "stats": { "n": 42, "min": -15.2, "max": -11.8,
                 "first_date": "...", "last_date": "..." },
      "series": [ { "date": "...", "wse": -14.9 }, ... ]
    }
  ]
}
```

## Compacter les données

Le site ne lit qu'une fraction infime des sorties : `U1` et `V1` côté
FLOW, `hsign`, `wlength`, `period` et `dir` côté WAVE, à **un** pas de
temps. Tout le reste — `S1`, `R1`, `RHO`, les contraintes de fond, 23
des 24 pas de temps, les couches non affichées — n'est jamais servi.

### Contrôler l'archive

Avant un traitement long, un balayage des seuls en-têtes repère les
runs incomplets en quelques minutes :

```bash
python pipeline/check_runs.py             # rapport
python pipeline/check_runs.py --csv bad.csv   # export des runs suspects
```

L'outil compare chaque run à la structure **majoritaire** de l'archive
et signale ce qui s'en écarte : pas de temps manquants, couches
absentes, variable non écrite, fichier illisible. Une sortie tronquée
révèle généralement une simulation interrompue ou qui n'a pas
convergé — l'information vaut bien au-delà du site, et le fichier
`.tri-diag` correspondant en donne la raison.

Ces runs ne bloquent pas le compactage : ils sont signalés, laissés
vides, et le site retombe pour eux sur les NetCDF d'origine.

### Compacter

L'index doit d'abord pointer vers vos simulations : le dépôt est livré
avec un index de **démonstration** (chemins `<demo>/…`) pour que le
site affiche quelque chose au premier lancement. Reconstruisez-le avant
de compacter, sinon la commande s'arrête avec un message explicite.

```bash
python pipeline/scenario_index.py                # index sur les vraies sorties
python pipeline/compact.py --dry-run             # estime la taille
python pipeline/compact.py --limit 5             # essai sur 5 scénarios
python pipeline/compact.py --layers 0,9 --time -1   # surface + fond
```

`--layers` prend des **indices à partir de 0** : `0` est la première
couche, `9` la dixième. L'interface, elle, numérote à partir de 1 —
d'où le récapitulatif affiché au lancement, qui rappelle la
correspondance. Les numéros d'origine sont conservés dans le fichier,
si bien que le sélecteur du site affiche « layer 10/10 » et non
« layer 2/2 » après un compactage sur deux couches.

Si le compactage s'interrompt — coupure, disque démonté, erreur de
lecture —, `--resume` reprend là où il s'est arrêté au lieu de tout
recommencer :

```bash
python pipeline/compact.py --layers 0,9 --resume
```

Le fichier existant n'est réutilisé que si sa liste de scénarios et ses
couches correspondent exactement à la demande ; sinon il est
reconstruit, pour éviter un mélange silencieux de paramètres.

Les runs défectueux (sortie tronquée, dimension vide, fichier corrompu)
sont **signalés et laissés vides** plutôt que d'interrompre le
traitement. En revanche, si les premiers scénarios échouent **tous**,
le compactage s'arrête immédiatement : ce n'est alors pas un problème
de données mais de code ou de configuration, et il vaut mieux le savoir
tout de suite qu'après plusieurs heures : sur 790 simulations, un seul run abîmé ne doit pas coûter
plusieurs heures. Le site retombe automatiquement sur les NetCDF
d'origine pour ces scénarios-là.

`--time -1` conserve le dernier pas (valeur par défaut). Le fichier
compact ne contenant plus qu'un instant, le sélecteur de pas de temps
disparaît de l'interface.

Le fichier produit rassemble **tous les scénarios** et remplace les
790 paires de NetCDF :

| | Volume |
|---|---|
| Sorties Delft3D complètes | ≈ 208 Go |
| Compact, couche de surface | ≈ 280 Mo |
| Compact, 3 couches | ≈ 460 Mo |
| Compact, 10 couches | ≈ 1,1 Go |

Un facteur d'environ **750** pour la surface seule. Quatre mécanismes
s'additionnent :

- **Seuls les champs affichés** sont conservés, à un pas de temps et
  aux couches choisies.
- **Les coordonnées sont stockées une fois**, en degrés, partagées par
  tous les scénarios — la grille est identique d'un run à l'autre.
- **Les vitesses sont déjà projetées** en composantes est/nord : la
  rotation ksi/eta et la convergence des méridiens sont appliquées au
  compactage, plus à l'affichage.
- **Encodage en entiers 16 bits** avec facteur d'échelle (convention CF
  `scale_factor`) puis compression zlib. Le pas est de 0,2 mm/s sur une
  vitesse et 0,2 mm sur une hauteur de vague, très au-delà de la
  précision du modèle. Le plafond (32 767 × pas) est choisi bien
  au-dessus de toute valeur plausible, et tout écrêtage est signalé en
  fin de traitement.

**Vérification par relecture.** Dès le premier scénario écrit, le
fichier est relu et comparé à la source ; un écart supérieur à
quelques pas de quantification interrompt le compactage. Une erreur
d'encodage est ainsi détectée en quelques secondes plutôt qu'après des
heures. Piège à connaître si vous modifiez ce code : netCDF4 applique
`scale_factor` **automatiquement à l'écriture**, d'où l'appel à
`set_auto_maskandscale(False)` sur les variables déjà encodées — sans
lui, la division a lieu deux fois, l'entier déborde, et les champs
relus sont absurdes sans le moindre message.

Les mailles sèches restent présentes avec une valeur nulle : ce sont
elles qui dessinent le trait de côte, et elles se compressent presque
gratuitement.

### Format retenu

**NetCDF4 unique, une dimension `scenario`.** Plutôt que 790 fichiers,
un seul, découpé en chunks d'un scénario : le serveur l'ouvre une fois
au démarrage et servir une couche revient à lire quelques dizaines de
kilo-octets. C'est ce qui rend le parcours de la frise temporelle
instantané, là où l'ouverture d'un NetCDF de 250 Mo prenait plusieurs
secondes.

Le choix de NetCDF plutôt que Zarr ou Parquet tient à trois raisons :
la donnée est matricielle et non tabulaire (Parquet convient mal) ;
Zarr apporte le découpage en objets, utile en stockage cloud mais
superflu pour 300 Mo sur un disque local ; et NetCDF reste lisible avec
les outils que tu utilises déjà (`ncdump`, xarray, ta propre toolbox),
ce qui garde le fichier exploitable hors du site.

Le serveur bascule automatiquement sur `data/compact.nc` dès qu'il
existe, et retombe sur les NetCDF d'origine sinon — les deux chemins
produisent la même charge utile. L'archive complète reste donc
nécessaire pour tout le reste de la thèse, mais **plus pour faire
tourner le site** : à 280 Mo, il devient déployable sur une petite
machine virtuelle sans transférer les 208 Go.

## Déploiement

### Ce qui peut aller sur GitHub — et ce qui ne peut pas

**Le code, oui ; les données, non.** Avec 790 runs à environ 265 Mo la
paire (FLOW + WAVE), les simulations représentent près de 200 Go :
au-delà de toute limite raisonnable pour un dépôt Git, même avec LFS.
Le fichier compact (≈ 280 Mo, voir la section précédente) tient en
revanche sous la limite de 1 Go de GitHub Pages, ce qui rapproche une
vitrine statique — il resterait à pré-calculer les rasters, le
navigateur ne sachant pas lire un NetCDF.
Le `.gitignore` fourni exclut `*.nc`, `data/*.json`, `.netrc` et les
fichiers macOS `._*`.

### Site statique complet (GitHub Pages)

**GitHub Pages ne sert que des fichiers statiques** : aucun code
serveur ne s'y exécute, et un navigateur ne sait ni lire un NetCDF ni
interpoler. La solution est de **pré-calculer** ce que l'API renvoie
déjà — une image géoréférencée et un jeu de flèches par scénario et par
couche :

```bash
python pipeline/export_static.py            # -> site/
python pipeline/export_static.py --limit 20 # essai rapide
```

Taille mesurée pour les 790 scénarios × 5 couches (courants sur deux
niveaux, hauteur, longueur d'onde, période) :

| Quantification | Rasters | Flèches | Total |
|---|---|---|---|
| 64 couleurs (défaut) | ~54 Mo | ~32 Mo | **~86 Mo** |
| aucune (`--colors 0`) | ~83 Mo | ~32 Mo | ~115 Mo |

Soit moins de 10 % de la limite de 1 Go. À 64 couleurs, l'écart avec le
rendu exact est d'un niveau RGB sur 255 en moyenne — invisible.

**Ce qui fonctionne à l'identique** : niveaux SWOT, série temporelle,
carte, imagerie GIBS, météo, appariement des scénarios et frise
temporelle. L'appariement — une recherche du plus proche voisin sur
quatre paramètres — est refait en JavaScript avec la même métrique que
le serveur (normalisation par l'étendue, direction circulaire), à
partir du même index.

**Ce qui change** : le bouton de mise à jour disparaît, faute de
serveur. Le pipeline tourne en local et l'on publie le résultat. Les
bornes de couleur sont en outre **communes à tous les scénarios**,
calculées au 95ᵉ centile sur un échantillon : les couleurs deviennent
comparables d'un scénario à l'autre, ce qui est plus juste pour
parcourir la frise.

### Publier le site statique

**1. Vérifier en local.** Les `fetch` ne fonctionnent pas depuis
`file://`, il faut un petit serveur :

```bash
cd site && python -m http.server 8080     # http://localhost:8080
```

**2. Créer le dépôt** (une seule fois). Depuis la **racine du projet**,
pas depuis `site/` :

```bash
cd ~/Desktop/lake-eyre-dashboard
git init -b main
git add -A
git status --short | head -20      # vérifier avant de valider
git commit -m "Lake Eyre observatory"
```

Créer ensuite un dépôt vide sur github.com, puis :

```bash
git remote add origin https://github.com/VOTRE-COMPTE/lake-eyre-dashboard.git
git push -u origin main
```

Le `.gitignore` fourni écarte les granules, les sorties Delft3D, le
fichier compact et `~/.netrc` ; il conserve `site/img/`,
`site/layers/` et `site/data/`, dont Pages a besoin. Un
`git status --short` avant le premier commit reste la meilleure
vérification.

**3. Publier les mises à jour suivantes.**

```bash
git add site && git commit -m "Publish static site" && git push
```

Puis, une seule fois, dans *Settings → Pages*, choisir comme source
**GitHub Actions** : le workflow `.github/workflows/pages.yml` prend le
relais à chaque poussée touchant `site/`.

**4. Tenir à jour.** Le workflow `weather.yml` rafraîchit la météo
toutes les heures et met à jour `site/data/weather.json` — le scénario
affiché suit donc les conditions réelles, sans intervention. Pour une
nouvelle passe SWOT, il suffit de relancer le pipeline puis de recopier
le JSON, sans tout ré-exporter :

```bash
python pipeline/update_swot.py --download
cp data/swot_wse.json site/data/ && git add site && git commit && git push
```

Un ré-export complet n'est nécessaire que si les **simulations**
changent.

**Coût en historique.** Chaque ré-export ajoute ~86 Mo à l'historique
Git. C'est acceptable pour quelques régénérations (limite conseillée
par GitHub : 1 Go de dépôt), mais si vous ré-exportez souvent, poussez
plutôt `site/` sur une branche orpheline en force :

```bash
git push -f origin `git subtree split --prefix site main`:gh-pages
```

en réglant alors *Settings → Pages* sur cette branche. La contrepartie
est que le rafraîchissement horaire de la météo ne suit plus, puisqu'il
publie sur `main`. Évitez Git LFS, dont le quota de bande passante
gratuit est plus contraignant que Pages lui-même.

**Ce que télécharge un visiteur** : jamais les 86 Mo. Le site charge
l'index, la météo, la série SWOT, puis les seules images du scénario
affiché — de l'ordre de 300 Ko, plus 15 Ko par changement de couche ou
de position sur la frise.

### Recommandation : une petite machine virtuelle

Pour le site complet, il faut un serveur ayant accès au disque des
simulations. Deux pistes, dans cet ordre :

1. **ARDC Nectar Research Cloud** — gratuit pour les chercheurs
   affiliés à une université australienne, via le login institutionnel
   (AAF). L'essai démarre immédiatement, puis une allocation plus
   longue se demande sur le tableau de bord Nectar. C'est l'option la
   plus adaptée : hébergement australien, proche des données, et
   indépendant d'un poste de travail.
2. **Le service informatique de ton université** — beaucoup proposent
   une VM ou un hébergement web pour les projets de recherche, avec
   sauvegarde et nom de domaine institutionnel.

Un service commercial (VPS à quelques euros par mois) fonctionne aussi,
mais suppose de transférer les 200 Go de simulations ou de ne déployer
que les scénarios utiles.

### Mise en ligne

Le dossier `deploy/` contient le nécessaire :

```bash
pip install gunicorn
gunicorn -c deploy/gunicorn.conf.py deploy.wsgi:app
```

- `deploy/wsgi.py` — point d'entrée WSGI. Le serveur intégré de Flask
  (`python run.py`) convient au poste de travail, pas à une mise en
  ligne.
- `deploy/gunicorn.conf.py` — un seul worker, plusieurs threads : le
  cache des champs vit en mémoire du processus, plusieurs workers
  reliraient les NetCDF sans bénéfice.
- `deploy/lake-eyre.service` — unité systemd (démarrage automatique,
  redémarrage en cas d'échec, écriture limitée à `data/`).
- `deploy/nginx.conf` — reverse proxy, avec HTTPS via certbot et un
  exemple d'accès restreint par mot de passe, utile pour un site
  réservé aux superviseurs.

**Avant d'exposer le site publiquement** : passer `allow_refresh` à
`false` dans `config.yaml`, ou définir `LKE_ALLOW_REFRESH=0` (déjà fait
dans l'unité systemd fournie). Ce bouton lance un sous-processus et
déclenche des téléchargements ; il n'a rien à faire entre les mains
d'un visiteur anonyme. Le bouton disparaît alors de l'interface.

Le pipeline continue de tourner par cron sur la machine qui détient les
données, indépendamment du serveur web.

### Avant le premier commit

Ton `SWOT_Downloader.py` d'origine contenait des identifiants Earthdata
en clair. Ils ne sont pas dans ce dépôt, mais si tu ajoutes tes autres
scripts, vérifie-les — un secret publié reste dans l'historique Git même
après suppression, et doit être considéré comme compromis.

## Note sur les sites d'extraction

Le point extrait jusqu'à présent sous le nom « Belt Bay » (137,560 °E)
se trouve en réalité dans **Madigan Gulf**, à environ 52 km à l'est du
véritable Belt Bay (137,028 °E). Les deux sous-bassins sont désormais
configurés sous leurs noms corrects, et la série déjà extraite reste
valable — seule son étiquette change.

La clé du cache d'extraction ne dépend plus du nom mais des seules
coordonnées, si bien que ce renommage n'entraîne aucun retraitement ;
un cache produit par une version antérieure est repris automatiquement.
Belt Bay, qui contient le point bas du lac, sert par défaut de
référence de niveau pour l'appariement des scénarios
(`scenarios.wlvl_site`).

## Notes d'intégration

- `SWOT_toolbox` est intégrée sans modification, **à une exception
  près** : dans `__init__.py`, l'import de `SWOT_plot` est rendu
  optionnel (try/except) pour que le serveur n'exige pas geopandas /
  contextily / folium / plotly. En notebook, rien ne change.
- `SWOT_Downloader.py` n'a pas été copié : sa logique (motifs de
  granules, `short_name`) vit désormais dans `config.yaml` +
  `update_swot.py --download`, sans identifiants en dur.
- `python tests/test_pipeline_wiring.py` vérifie le contrat
  pipeline ↔ toolbox (paramètres transmis, filtrage temporel,
  datum_offset, schéma JSON) ; `python tests/test_incremental.py`
  vérifie le cache incrémental, la fidélité des filtres aval et la
  fenêtre de recherche. Aucun des deux ne nécessite de granules.
- Granules retraités : une version retraitée porte un nom de fichier
  différent (CRID) et sera donc téléchargée comme « nouvelle » à côté
  de l'ancienne, ce qui peut dupliquer une date dans la série — même
  comportement que le téléchargement manuel actuel. Supprimer
  l'ancienne version du disque suffit à l'écarter.

## Étapes suivantes

- Superposer le champ Delft3D à la carte Leaflet, ce qui suppose de
  reprojeter les coordonnées du modèle (mètres) en WGS84.
- Extraire le niveau simulé au droit de Belt Bay pour le comparer
  directement à la série SWOT.
- Interpoler entre scénarios voisins plutôt que de prendre le plus
  proche : avec un plan LHS à 3 % de couverture, une pondération des
  quelques voisins les plus proches serait plus fidèle qu'un choix
  unique.
- Étendre le plan vers les bas niveaux : la plage simulée s'arrête à
  −14,0 m alors que la série observée est descendue à −14,11 m.
