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

    pg.click('.section-btn[data-section="people"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("clic People and country : Country and people",
          s["panel"] == ["tab-country"] and s["navs"] == ["people"] and s["hash"] == "#country", s)
    pg.click('.tab[data-tab="culture"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("sous-onglet Peoples", s["panel"] == ["tab-culture"] and s["navs"] == ["people"], s)
    n_rows = pg.locator("#tab-culture .people-table tbody tr").count()
    check("tableau des nations injecté (5 lignes)", n_rows == 5, n_rows)

    pg.click('#tab-culture a.cite[href="#acref-dodd2012"]'); pg.wait_for_timeout(600)
    s = state(pg)
    check("renvoi bibliographique", s["hash"] == "#acref-dodd2012" and s["panel"] == ["tab-culture"], s)
    vis = pg.evaluate("() => { const r = document.getElementById('acref-dodd2012').getBoundingClientRect(); return r.top >= -2 && r.top < innerHeight; }")
    check("référence amenée à l'écran", vis)

    pg.click('.section-btn[data-section="lake"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("clic Lake : The lake", s["panel"] == ["tab-lake-overview"] and s["navs"] == ["lake"], s)

    pg.click('.section-btn[data-section="science"]'); pg.wait_for_timeout(200)
    pg.click('.tab[data-tab="hydrodynamics"]'); pg.wait_for_timeout(200)
    pg.click('.section-btn[data-section="people"]'); pg.wait_for_timeout(200)
    pg.click('.section-btn[data-section="science"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("retour sur le dernier onglet de Science", s["panel"] == ["tab-dashboard"], s)
    pg.goto(BASE + "#floods"); pg.wait_for_timeout(500)
    s = state(pg)
    check("sous-onglet Fillings", s["panel"] == ["tab-floods"] and s["navs"] == ["lake"], s)
    n = pg.evaluate("() => document.querySelectorAll('#tab-floods .fl-year').length")
    check("frise des remplissages", n == 6, n)
    pg.goto(BASE + "#data"); pg.wait_for_timeout(400)
    check("page Data and citation",
          pg.evaluate("() => document.getElementById('cite-date').textContent.length > 4"))
    pg.goto(BASE + "#rain-to-lake"); pg.wait_for_timeout(600)
    check("bloc vivant du temps de parcours",
          pg.evaluate("() => Boolean(document.getElementById('travel-live'))"))
    pg.goto(BASE + "#hydrodynamics"); pg.wait_for_timeout(400)
    s = state(pg)
    check("Hydrodynamics dans Science", s["panel"] == ["tab-dashboard"] and s["navs"] == ["science"], s)

    # Les deux lectures du panneau partagé : une seule carte, des cartes
    # de données propres à chacune. Masquer est fait par le CSS, donc on
    # interroge la mise en page réelle et non l'attribut hidden.
    #
    # Sans données, #dashboard reste masqué au profit de l'état vide, et
    # tout y serait invisible pour la mauvaise raison : le test
    # découvrirait une scission correcte même si le CSS ne faisait rien.
    # On le découvre donc à la main avant de mesurer.
    pg.evaluate("""() => {
      document.getElementById('empty-state').hidden = true;
      document.getElementById('dashboard').hidden = false;
    }""")
    pg.wait_for_timeout(100)

    def shown(sel):
        return pg.evaluate("(s) => { const e = document.querySelector(s);"
                           " return Boolean(e && e.getClientRects().length); }", sel)

    # Garde-fou : la mesure doit savoir voir quelque chose.
    check("l'état vide écarté, le tableau de bord est mesurable",
          shown("#dashboard"))
    check("Hydrodynamics : scénario Delft3D visible", shown(".model-card"))
    check("Hydrodynamics : série SWOT masquée", not shown(".level-series"))
    check("Hydrodynamics : carte partagée non masquée par le CSS",
          pg.evaluate("() => getComputedStyle(document.querySelector"
                      "('.map-card')).display !== 'none'"))
    pg.click('.tab[data-tab="satellite"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("Satellite imaging dans Science",
          s["panel"] == ["tab-dashboard"] and s["navs"] == ["science"], s)
    check("Satellite : série SWOT visible", shown(".level-series"))
    check("Satellite : scénario Delft3D masqué", not shown(".model-card"))
    check("Satellite : carte partagée non masquée par le CSS",
          pg.evaluate("() => getComputedStyle(document.querySelector"
                      "('.map-card')).display !== 'none'"))
    check("une seule carte Leaflet dans la page",
          pg.evaluate("() => document.querySelectorAll('#map').length") == 1)

    pg.goto(BASE + "#hydrology"); pg.wait_for_timeout(300)
    s = state(pg)
    check("Hydrological modelling, encore vide",
          s["panel"] == ["tab-hydrology"] and s["navs"] == ["science"], s)
    pg.goto(BASE + "#group"); pg.wait_for_timeout(400)
    s = state(pg)
    check("Research group est une partie a elle seule",
          s["panel"] == ["tab-group"] and s["navs"] == [], s)
    check("et n'est plus un onglet de Science",
          pg.evaluate("() => !document.querySelector('.tab[data-tab=\"group\"]')"))
    n = pg.evaluate("() => document.querySelectorAll('#tab-group .person').length")
    check("cinq personnes dans le groupe", n == 5, n)
    check("aucun ORCID inventé",
          pg.evaluate("() => document.querySelectorAll('#tab-group a[href*=\"orcid.org\"]').length") == 0)

    pg.click('.section-btn[data-section="basin"]'); pg.wait_for_timeout(200)
    pg.click('.tab[data-tab="weather"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("sous-onglet Weather dans Basin", s["panel"] == ["tab-weather"] and s["navs"] == ["basin"], s)
    check("panneau BOM dans Weather",
          pg.evaluate("() => document.getElementById('tab-weather').contains(document.getElementById('weather-strip'))"))
    pg.click('.tab[data-tab="rainfall"]'); pg.wait_for_timeout(200)
    s = state(pg)
    check("sous-onglet Rainfall dans Basin", s["panel"] == ["tab-rainfall"] and s["navs"] == ["basin"], s)
    # Anciennes adresses : #modelling a ete partage avant la scission
    for old_hash, want in (("#observatory", "tab-dashboard"), ("#modelling", "tab-dashboard"),
                           ("#rain-rivers", "tab-river-flow")):
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
                    ("#hydrodynamics", "tab-dashboard"), ("#satellite", "tab-dashboard"),
                    ("#hydrology", "tab-hydrology"), ("#group", "tab-group"),
                    ("#floods", "tab-floods"),
                    ("#lake-overview", "tab-lake-overview"), ("#country", "tab-country"),
                    ("#rain-to-lake", "tab-rain-to-lake"), ("#data", "tab-data")):
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
    check("sous-onglet Stories", s["panel"] == ["tab-stories"] and s["navs"] == ["people"], s)
    pg.click('.wordmark'); pg.wait_for_timeout(400)
    s = state(pg)
    check("nom du site : retour à l'accueil", s["panel"] == ["tab-home"], s)

    pg.goto(BASE + "#fauna-flora"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="birds"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet Bird sightings", s["panel"] == ["tab-birds"] and s["navs"] == ["nature"], s)
    href = pg.evaluate("() => document.querySelector('#tab-birds .submit-btn').href")
    check("bouton Submit an observation vers eBird", href == "https://ebird.org/submit", href)
    pg.click('.tab[data-tab="fauna-flora"]'); pg.wait_for_timeout(300)
    n = pg.evaluate("() => document.querySelectorAll('#tab-fauna-flora .obs-block').length")
    check("sept groupes avec observations", n == 7, n)
    pg.goto(BASE + "#catchment"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="river-flow"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet River flow", s["panel"] == ["tab-river-flow"] and s["navs"] == ["basin"], s)
    pg.goto(BASE + "#fauna-flora"); pg.wait_for_timeout(400)
    pg.click('.tab[data-tab="birds"]'); pg.wait_for_timeout(300)
    pg.click('.tab[data-tab="inaturalist"]'); pg.wait_for_timeout(300)
    s = state(pg)
    check("onglet iNaturalist", s["panel"] == ["tab-inaturalist"] and s["navs"] == ["nature"], s)
    check("plus de couche Birds sur la carte partagée",
          pg.evaluate("() => !document.getElementById('birds-seg')"))

    real = [e for e in errors if "fetch" not in e.lower() and "json" not in e.lower()]
    check("aucune erreur JavaScript de navigation", not real, real[:3])
    b.close()

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} vérifications réussies")
raise SystemExit(1 if failed else 0)
