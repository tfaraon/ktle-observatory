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
    check("retour sur le dernier onglet de Science", s["panel"] == ["tab-hydrodynamics"], s)
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
    check("Hydrodynamics est son propre panneau",
          s["panel"] == ["tab-hydrodynamics"] and s["navs"] == ["science"], s)

    # Sans donnees, le corps du tableau de bord reste masque au profit de
    # l'etat vide, et tout y serait invisible pour la mauvaise raison. On
    # le decouvre a la main avant de mesurer.
    pg.evaluate("""() => {
      document.querySelectorAll('.empty-state').forEach(e => { e.hidden = true; });
      document.querySelectorAll('.dashboard-body').forEach(e => { e.hidden = false; });
    }""")
    pg.wait_for_timeout(100)

    def inside(panel, sel):
        return pg.evaluate("([p, s]) => { const e = document.querySelector('#' + p + ' ' + s);"
                           " return Boolean(e); }", [panel, sel])

    check("Hydrodynamics : scenario Delft3D", inside("tab-hydrodynamics", ".model-card"))
    check("Hydrodynamics : selecteur de couche", inside("tab-hydrodynamics", "#model-seg"))
    check("Hydrodynamics : lecture au survol", inside("tab-hydrodynamics", "#map-readout"))
    check("Hydrodynamics : frise temporelle", inside("tab-hydrodynamics", "#timeline"))
    check("Hydrodynamics : sa carte", inside("tab-hydrodynamics", "#map-hydro"))
    check("Hydrodynamics : note de methode", inside("tab-hydrodynamics", ".method-note"))
    check("Hydrodynamics : pas la serie SWOT", not inside("tab-hydrodynamics", ".level-series"))
    check("Hydrodynamics : pas les reglages d'imagerie",
          not inside("tab-hydrodynamics", "#imagery-controls"))

    pg.goto(BASE + "#satellite"); pg.wait_for_timeout(400)
    s = state(pg)
    check("Satellite imaging est son propre panneau",
          s["panel"] == ["tab-satellite"] and s["navs"] == ["science"], s)
    pg.evaluate("""() => {
      document.querySelectorAll('.empty-state').forEach(e => { e.hidden = true; });
      document.querySelectorAll('.dashboard-body').forEach(e => { e.hidden = false; });
    }""")
    pg.wait_for_timeout(100)
    check("Satellite : serie SWOT", inside("tab-satellite", ".level-series"))
    check("Satellite : surface en eau", inside("tab-satellite", "#area-card"))
    check("Satellite : reglages d'imagerie", inside("tab-satellite", "#imagery-controls"))
    check("Satellite : sa carte", inside("tab-satellite", "#map-sat"))
    check("Satellite : pas le scenario Delft3D", not inside("tab-satellite", ".model-card"))
    check("Satellite : pas la frise temporelle", not inside("tab-satellite", "#timeline"))
    check("Satellite : selecteur d'etendue d'eau", inside("tab-satellite", "#extent-seg"))
    check("Satellite : note de methode", inside("tab-satellite", ".method-note"))
    check("Satellite : note de l'etendue", inside("tab-satellite", "#extent-note"))
    check("l'etendue d'eau n'est plus une couche du modele",
          pg.evaluate("() => !document.querySelector('[data-model=\"water\"]')"))
    check("chaque carte a sa legende",
          pg.evaluate("() => document.querySelectorAll('#map-legend, #map-legend-sat').length") == 2)
    check("la hauteur des cartes tient a une classe",
          pg.evaluate("() => document.querySelectorAll('.map-pane').length") == 2)

    # Un identifiant en double ne casse rien visiblement : getElementById
    # rend le premier, le second reste mort. C'est arrive en dupliquant
    # la carte du graphique SWOT lors de la scission des panneaux.
    dup = pg.evaluate("""() => {
      const seen = {}, bad = [];
      document.querySelectorAll('[id]').forEach(e => {
        seen[e.id] = (seen[e.id] || 0) + 1;
        if (seen[e.id] === 2) bad.push(e.id);
      });
      return bad;
    }""")
    check("aucun identifiant en double dans la page", not dup, dup)

    check("deux conteneurs de carte distincts",
          pg.evaluate("() => document.querySelectorAll('#map-sat, #map-hydro').length") == 2)
    check("plus de conteneur partage",
          pg.evaluate("() => !document.getElementById('map')"))
    check("chaque carte a son segment de fond",
          pg.evaluate("() => document.querySelectorAll('#base-seg-sat, #base-seg-hydro').length") == 2)

    # Un renvoi de note de methode ouvre Methods et y defile
    for anchor in ("me-swot", "me-model", "me-imagery", "me-matching"):
        # Le defilement est anime : une ancre a 4500 px met un moment a
        # arriver, et un test impatient la declare hors ecran.
        pg.goto(BASE + "#" + anchor); pg.wait_for_timeout(1000)
        st = state(pg)
        ok = st["panel"] == ["tab-methods"] and st["hash"] == "#" + anchor
        vis = pg.evaluate("(a) => { const e = document.getElementById(a);"
                          " if (!e) return false; const r = e.getBoundingClientRect();"
                          " return r.top >= -2 && r.top < innerHeight; }", anchor)
        check(f"renvoi #{anchor} vers Methods", ok and vis, st)

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
    for old_hash, want in (("#observatory", "tab-hydrodynamics"), ("#modelling", "tab-hydrodynamics"),
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
                    ("#hydrodynamics", "tab-hydrodynamics"), ("#satellite", "tab-satellite"),
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
