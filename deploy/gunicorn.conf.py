"""Configuration gunicorn pour l'observatoire.

Un seul worker suffit : le service est en lecture seule et le cache des
champs (_FIELD_CACHE) est en memoire, donc partage entre les requetes
d'un meme processus. Plusieurs workers multiplieraient la lecture des
NetCDF sans benefice.
"""
bind = "127.0.0.1:8000"
workers = 1
threads = 4
# La lecture d'un champ FLOW (fichier de ~250 Mo) peut etre lente au
# premier appel, avant la mise en cache.
timeout = 180
accesslog = "-"
errorlog = "-"
loglevel = "info"
