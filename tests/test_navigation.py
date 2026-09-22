#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Navigation du site dans un vrai navigateur sans tete (Playwright).

Verifie l'ouverture, les trois parties, les onglets, les liens directs,
les renvois bibliographiques et le changement d'adresse en cours de
visite. C'est ce test qui a revele qu'un « const » global n'est pas une
propriete de window. Il est ignore si Playwright n'est pas installe.

Execution :  python tests/test_navigation.py
"""

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright absent : test de navigation ignoré "
          "(pip install playwright && playwright install chromium)")
    sys.exit(0)

BASE = (Path(__file__).resolve().parent.parent / "frontend" / "index.html").as_uri()
STUB = "window.L = new Proxy(function(){}, {get:()=>()=>({addTo(){return this},on(){return this},setView(){return this}})});"
errors = []

def state(page):
    return page.evaluate("""() => ({
      panel: [...document.querySelectorAll('.tab-panel')].filter(p => !p.hidden).map(p => p.id),
      section: [...document.querySelectorAll('.section-btn.active')].map(b => b.dataset.section),
      navs: [...document.querySelectorAll('[data-for]')].filter(n => !n.hidden).map(n => n.dataset.for),
      hash: location.hash,
    })""")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # Pas de réseau : bibliothèques externes remplacées par des souches
    pg.route("**/*unpkg.com/**", lambda r: r.fulfill(body=STUB, content_type="application/javascript"))
    pg.route("**/*cdn.plot.ly/**", lambda r: r.fulfill(body="window.Plotly={newPlot(){},Plots:{resize(){}}};", content_type="application/javascript"))
    pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))

    checks = []
    def check(label, cond, detail=""):
        checks.append((label, cond)); print(("  OK   " if cond else "  ECHEC") + f" {label} {detail if not cond else ''}")

    pg.goto(BASE); pg.wait_for_timeout(400)
    s = state(pg)
    check("ouverture sur l'accueil", s["panel"] == ["tab-home"] and s["section"] == [], s)

    pg.click('.section-btn[data-section="culture"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("clic Aboriginal Culture", s["panel"] == ["tab-culture"] and s["navs"] == ["culture"] and s["hash"] == "#culture", s)
    n_rows = pg.locator("#tab-culture .people-table tbody tr").count()
    check("tableau des nations injecté (5 lignes)", n_rows == 5, n_rows)

    pg.click('#tab-culture a.cite[href="#acref-dodd2012"]'); pg.wait_for_timeout(600)
    s = state(pg)
    check("renvoi bibliographique", s["hash"] == "#acref-dodd2012" and s["panel"] == ["tab-culture"], s)
    vis = pg.evaluate("() => { const r = document.getElementById('acref-dodd2012').getBoundingClientRect(); return r.top >= -2 && r.top < innerHeight; }")
    check("référence amenée à l'écran", vis)

    pg.click('.section-btn[data-section="lake"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("clic The lake : Natural history", s["panel"] == ["tab-natural-history"] and s["navs"] == ["lake"], s)

    pg.click('.tab[data-tab="methods"]'); pg.wait_for_timeout(200)
    pg.click('.section-btn[data-section="culture"]'); pg.wait_for_timeout(200)
    pg.click('.section-btn[data-section="lake"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("retour sur le dernier onglet de The lake", s["panel"] == ["tab-methods"], s)
    pg.click('.tab[data-tab="modelling"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("sous-onglet Modelling", s["panel"] == ["tab-modelling"] and s["navs"] == ["lake"], s)
    pg.click('.section-btn[data-section="climate"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("clic Climate and meteorology : Weather", s["panel"] == ["tab-weather"] and s["navs"] == ["climate"], s)
    check("panneau BOM dans Weather",
          pg.evaluate("() => document.getElementById('tab-weather').contains(document.getElementById('weather-strip'))"))
    pg.click('.tab[data-tab="rainfall"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("sous-onglet Rainfall", s["panel"] == ["tab-rainfall"] and s["navs"] == ["climate"], s)
    for old_hash, want in (("#observatory", "tab-modelling"), ("#rain-rivers", "tab-river-flow")):
        pg.goto(BASE + old_hash); pg.wait_for_timeout(400)
        s = state(pg)
        check(f"ancienne adresse {old_hash}", s["panel"] == [want], s)

    for h, want in (("#nh-geology", "tab-natural-history"), ("#acref-qldparl2023", "tab-culture"),
                    ("#culture", "tab-culture"), ("#publications", "tab-publications"),
                    ("#catchment", "tab-catchment"), ("#ct-rivers", "tab-catchment"),
                    ("#stories", "tab-stories"), ("#st-arabana", "tab-stories"),
                    ("#home", "tab-home"), ("#fauna-flora", "tab-fauna-flora"),
                    ("#ff-animals", "tab-fauna-flora"), ("#birds", "tab-birds"),
                    ("#inaturalist", "tab-inaturalist"), ("#river-flow", "tab-river-flow"),
                    ("#weather", "tab-weather"), ("#rainfall", "tab-rainfall"),
                    ("#modelling", "tab-modelling")):
        pg.goto(BASE + h); pg.wait_for_timeout(500)
        s = state(pg)
        check(f"lien direct {h}", s["panel"] == [want] and s["hash"] == h, s)

    pg.goto(BASE); pg.wait_for_timeout(300)
    pg.evaluate("() => { location.hash = '#ac-basin'; }"); pg.wait_for_timeout(500)
    s = state(pg)
    check("changement d'adresse en cours de visite", s["panel"] == ["tab-culture"], s)

    pg.goto(BASE + "#culture"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="stories"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("sous-onglet Stories", s["panel"] == ["tab-stories"] and s["navs"] == ["culture"], s)
    pg.click('.wordmark'); pg.wait_for_timeout(400)
    s = state(pg)
    check("nom du site : retour à l'accueil", s["panel"] == ["tab-home"], s)

    pg.goto(BASE + "#fauna-flora"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="birds"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet Bird sightings", s["panel"] == ["tab-birds"] and s["navs"] == ["fauna-flora"], s)
    href = pg.evaluate("() => document.querySelector('#tab-birds .submit-btn').href")
    check("bouton Submit an observation vers eBird", href == "https://ebird.org/submit", href)
    pg.click('.tab[data-tab="fauna-flora"]'); pg.wait_for_timeout(300)
    n = pg.evaluate("() => document.querySelectorAll('#tab-fauna-flora .obs-block').length")
    check("sept groupes avec observations", n == 7, n)
    pg.goto(BASE + "#catchment"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="river-flow"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet River flow", s["panel"] == ["tab-river-flow"] and s["navs"] == ["catchment"], s)
    pg.goto(BASE + "#fauna-flora"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="birds"]'); pg.wait_for_timeout(300)
    pg.click('.tab[data-tab="inaturalist"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet iNaturalist", s["panel"] == ["tab-inaturalist"] and s["navs"] == ["fauna-flora"], s)
    check("plus de couche Birds sur la carte du Modelling",
          pg.evaluate("() => !document.getElementById('birds-seg')"))

    real = [e for e in errors if "fetch" not in e.lower() and "json" not in e.lower()]
    check("aucune erreur JavaScript de navigation", not real, real[:3])
    b.close()

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} vérifications réussies")
raise SystemExit(1 if failed else 0)
