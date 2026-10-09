#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rendu d'une figure a plusieurs vues, dans un vrai navigateur.

Trois photographies d'un meme sujet, par exemple Blanche Cup pour
l'emplacement « mound-spring », tiennent dans un seul emplacement. Ce
test verifie dans le navigateur ce qu'aucune lecture du code ne garantit
vraiment :

  - les trois images sont rendues, dans l'ordre du manifeste ;
  - chaque panneau porte sa lettre et sa legende propre ;
  - la legende de la figure vient du manifeste quand il en donne une,
    de la page sinon ;
  - un emplacement a une seule image garde le rendu simple d'avant ;
  - le texte de remplacement (alt) de chaque image n'est pas vide, et ne
    contient pas de balises ;
  - l'agrandissement d'un panneau montre la legende de CE panneau.

Ignore si Playwright n'est pas installe.

Execution :  python tests/test_figure_panels.py
"""

import functools
import json
import shutil
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright absent : test des panneaux ignoré "
          "(pip install playwright && playwright install chromium)")
    sys.exit(0)

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

LEAD = ("Blanche Cup, one of the mound springs on the arc that runs from "
        "Lake Callabonna to Dalhousie.")
PANELS = ["The pool at the summit of the mound",
          "The carbonate tail below the vent",
          "Reeds around the outflow"]

with tempfile.TemporaryDirectory() as td:
    work = Path(td) / "frontend"
    shutil.copytree(FRONTEND, work)

    # Trois images factices, et une quatrieme pour l'emplacement simple
    (work / "img" / "figures").mkdir(parents=True, exist_ok=True)
    for i, colour in enumerate([(120, 150, 110), (150, 130, 100), (110, 120, 150)]):
        name = "mound-spring.jpg" if i == 0 else f"mound-spring-{i + 1}.jpg"
        Image.new("RGB", (800, 600), colour).save(work / "img" / "figures" / name)
    Image.new("RGB", (800, 600), (90, 90, 90)).save(
        work / "img" / "figures" / "goyder-channel.jpg")

    manifest = json.loads((work / "figures.json").read_text(encoding="utf-8"))
    manifest["figures"]["mound-spring"] = {
        "credit": "Photograph: Thomas Faraon",
        "caption": LEAD,
        "images": [
            {"file": "figures/mound-spring.jpg", "caption": PANELS[0]},
            {"file": "figures/mound-spring-2.jpg", "caption": PANELS[1]},
            {"file": "figures/mound-spring-3.jpg", "caption": PANELS[2]},
        ],
    }
    # Emplacement a une seule image, sur la meme page : la legende
    # reste celle ecrite dans la page, faute de remplacement
    manifest["figures"]["goyder-channel"] = {
        "credit": "Photograph: Thomas Faraon",
        "file": "figures/goyder-channel.jpg",
    }
    (work / "figures.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Un serveur local, car figures.json est lu par fetch() : depuis une
    # adresse file://, Chromium le refuse et la figure resterait vide.
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(work))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"

    STUB = ("window.L = new Proxy(function(){}, {get:()=>()=>({addTo(){return this},"
            "on(){return this},setView(){return this}})});")
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/*unpkg.com/**", lambda r: r.fulfill(
            body=STUB, content_type="application/javascript"))
        pg.route("**/*cdn.plot.ly/**", lambda r: r.fulfill(
            body="window.Plotly={newPlot(){},Plots:{resize(){}}};",
            content_type="application/javascript"))
        pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(
            body="", content_type="text/css"))

        # La page « Natural history » porte mound-spring et salt-crust
        pg.goto(base + "#natural-history")
        # Lecture et attente dans le meme appel : l'onglet reinjecte son
        # HTML quand ses donnees arrivent, et une lecture faite entre
        # l'injection et fillFigures trouve un noeud deja remplace.
        fig = pg.wait_for_function(
            """() => {
              const el = document.querySelector("figure.fig[data-fig='mound-spring']");
              if (!el || el.dataset.filled !== '1') return null;
              const panels = [...el.querySelectorAll('.fig-panel')];
              if (panels.length !== 3) return null;
              return {
                n: panels.length,
                srcs: panels.map(p => p.querySelector('img').getAttribute('src')),
                alts: panels.map(p => p.querySelector('img').alt),
                caps: panels.map(p => p.querySelector('.fig-panel-cap').textContent.trim()),
                lead: el.querySelector('figcaption').textContent.trim(),
                grid: getComputedStyle(el.querySelector('.fig-panels')).display,
                widths: panels.map(p => p.querySelector('img').naturalWidth),
              };
            }""", timeout=20000).json_value()

        assert fig["n"] == 3, fig
        assert fig["srcs"] == ["img/figures/mound-spring.jpg",
                              "img/figures/mound-spring-2.jpg",
                              "img/figures/mound-spring-3.jpg"], fig["srcs"]
        for i, cap in enumerate(fig["caps"]):
            letter = "abc"[i]
            assert cap.startswith(f"({letter})"), cap
            assert PANELS[i] in cap, cap
        assert fig["lead"].startswith("Blanche Cup"), fig["lead"]
        assert "Photograph: Thomas Faraon" in fig["lead"]
        # alt non vide et sans balise : c'est ce que lit un lecteur d'écran
        for alt in fig["alts"]:
            assert alt and "<" not in alt, alt
            assert "Blanche Cup" in alt, alt
        assert fig["grid"] == "grid", fig["grid"]

        # Les images sont réellement chargées, pas des cadres cassés
        assert all(w > 0 for w in fig["widths"]), fig["widths"]

        # Emplacement à une seule image : rendu simple, légende de la page
        simple = pg.wait_for_function(
            """() => {
              const el = document.querySelector("figure.fig[data-fig='goyder-channel']");
              if (!el || el.dataset.filled !== '1') return null;
              return {panels: el.querySelectorAll('.fig-panel').length,
                      img: (el.querySelector('img') || {}).getAttribute
                           ? el.querySelector('img').getAttribute('src') : null,
                      cap: el.querySelector('figcaption').textContent.trim()};
            }""", timeout=20000).json_value()
        assert simple["panels"] == 0, simple
        assert simple["img"] == "img/figures/goyder-channel.jpg", simple
        assert "goyder channel" in simple["cap"].lower(), simple["cap"]

        # Agrandissement : la légende montrée est celle du panneau cliqué
        pg.click("figure.fig[data-fig='mound-spring'] .fig-panel:nth-child(2) img")
        box = pg.wait_for_function(
            """() => {
              const img = document.querySelector('.lightbox img');
              if (!img) return null;
              const cap = document.querySelector('.lightbox figcaption');
              return {src: img.getAttribute('src'),
                      cap: cap ? cap.textContent : ''};
            }""", timeout=8000).json_value()
        assert box["src"].endswith("mound-spring-2.jpg"), box
        assert PANELS[1] in box["cap"], box
        assert PANELS[0] not in box["cap"], "la légende de la figure entière ne doit pas s'afficher"

        b.close()
    httpd.shutdown()

    assert not errors, f"erreurs JavaScript : {errors[:3]}"

print("OK — trois vues rendues en panneaux lettrés avec leurs légendes, "
      "légende de figure prise du manifeste, emplacement simple inchangé, "
      "agrandissement sur la légende du panneau.")
