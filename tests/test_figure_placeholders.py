#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le cadre « Image to come » ne doit jamais atteindre un visiteur.

Un emplacement de figure sans image affiche, pendant le travail, un
cadre gris nommant le fichier attendu. C'est une aide utile en local et
une fuite en production : le site publie a montre « Image to come » et
un chemin interne sur les pages Methodes, Meteo et Debits, parce que le
drapeau du manifeste etait reste a true.

Le drapeau seul ne suffit donc pas, il faut le penser avant chaque
publication. Ce test verifie la regle qui l'accompagne : le cadre
s'affiche sur une machine de developpement et nulle part ailleurs.

Execution :  python tests/test_figure_placeholders.py
"""

import json
import mimetypes
import re
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PROD = "https://ktle-observatory.org"

# Leaflet et Plotly viennent d'un CDN : sans eux l'initialisation
# s'arrete avant le rendu des figures, et le test mesurerait le vide.
STUB = r"""
const chain = new Proxy(function(){}, {get:()=>()=>chain, apply:()=>chain});
window.L = new Proxy(function(){}, {
  get:(t,k)=> k==='Icon' ? {Default:{prototype:{},mergeOptions(){}}} : ()=>chain,
  apply:()=>chain});
window.Plotly = {newPlot(){}, Plots:{resize(){}}, relayout(){}, react(){}, purge(){}};
"""
BLOCK = re.compile(r"(unpkg\.com|cdn\.plot\.ly|fonts\.g|gibs\.earthdata|tile\.)")


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve_from_disk(route):
    """Sert le domaine publie depuis site/, pour eprouver ce cas sans reseau."""
    path = route.request.url.split("?")[0].split("#")[0][len(PROD):].lstrip("/")
    f = SITE / (path or "index.html")
    if not f.is_file():
        return route.fulfill(status=404, body="")
    route.fulfill(status=200, body=f.read_bytes(),
                  content_type=mimetypes.guess_type(str(f))[0] or "text/plain")


def count_frames(pg, url):
    pg.goto(url + "#methods")
    pg.wait_for_timeout(2200)
    return pg.evaluate("""() => ({
        frames: document.querySelectorAll('.fig-empty').length,
        leaks: (document.body.innerText.match(/Image to come/g) || []).length,
        paths: (document.body.innerText.match(/img\\/figures\\//g) || []).length,
    })""")


checks = []


def check(label, ok, detail=""):
    checks.append(ok)
    if not ok:
        print(f"ECHEC — {label}" + (f" : {detail}" if detail else ""))


# Le manifeste declare-t-il encore des emplacements sans image ? Sans
# cela le test passerait en ne mesurant rien.
figs = json.loads((SITE / "figures.json").read_text(encoding="utf-8"))["figures"]
page = (SITE / "index.html").read_text(encoding="utf-8")
page += (SITE / "methods.js").read_text(encoding="utf-8")
slots = set(re.findall(r'data-fig="([^"]+)"', page))
empty = sorted(s for s in slots if not figs.get(s, {}).get("file"))
check("au moins un emplacement sans image, sinon le test ne prouve rien",
      bool(empty), slots)

srv = ThreadingHTTPServer(("127.0.0.1", 8749),
                          partial(Quiet, directory=str(SITE)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 900})
        pg.add_init_script(STUB)
        pg.route(BLOCK, lambda r: r.fulfill(status=200, body="",
                                            content_type="text/plain"))

        local = count_frames(pg, "http://localhost:8749/index.html")
        check("le cadre reste disponible en local", local["frames"] >= 1, local)

        pg.route(re.compile(r"^" + re.escape(PROD) + "/"), serve_from_disk)
        prod = count_frames(pg, PROD + "/index.html")
        check("aucun cadre sur le domaine publie", prod["frames"] == 0, prod)
        check("« Image to come » n'atteint pas le visiteur", prod["leaks"] == 0, prod)
        check("aucun chemin de fichier interne affiche", prod["paths"] == 0, prod)
        b.close()
finally:
    srv.shutdown()

if not all(checks):
    print(f"\n{checks.count(False)}/{len(checks)} verifications en echec")
    sys.exit(1)
print(f"OK — {len(checks)} verifications : le cadre nommant un fichier attendu "
      f"s'affiche en local ({', '.join(empty)}) et disparait entierement sur le "
      "domaine publie, drapeau du manifeste compris.")
