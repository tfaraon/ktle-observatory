#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Page « From rain to lake » -> frontend/rain_to_lake.js

Elle relie les trois mesures que le site collecte deja : la pluie sur le
bassin, le debit aux stations et le niveau du lac. Le bloc
<div id="travel-live"> est rempli par app.js a partir des donnees du
jour ; le reste est du texte reference.

    python tools/build_rain_to_lake.py
"""

import refbuild

REFS = dict(refbuild.shared_refs([
    "badman1991a", "knighton1994", "costelloe2003", "rai2026b",
]))
REFS["faraon2026"] = (
    "Faraon et al. in preparation", "Faraon et al. (in preparation)",
    "Faraon, T. et al. (in preparation) Using satellite imagery of the Lake Eyre basin to "
    "understand hydrodynamics during the 2025 flood event.", None)
REFS["bom2025"] = (
    "BOM 2025", "The Bureau of Meteorology (2025)",
    "Bureau of Meteorology (2025) Financial year climate and water statement 2024&ndash;25, "
    "issued 25 July 2025, and Australia in February 2025, issued 3 March 2025.",
    "http://www.bom.gov.au/climate/current/")

SECTIONS = [
("Three measurements, one journey", "rl-three", [
"Rain that ends up in Kati Thanda falls, for the most part, a thousand kilometres away and months earlier, "
"over the Queensland headwaters of the Diamantina and Cooper Creek. Between that rain and the lake lies the "
"Channel Country, where the flood spreads across floodplains, waterholes and interdunal corridors, loses water "
"to infiltration and evaporation, and arrives attenuated and late {c:knighton1994,costelloe2003}. Cooper Creek, "
"the largest of the rivers, reached the lake only eleven times between 1890 and 1991 for this reason: the lakes "
"and swamps of its lower course must fill before anything flows on {c:badman1991a}.",
"This site measures the journey at three points. Rainfall over the whole basin comes from the SILO grids, "
"updated daily. Flow comes from the river gauges still operating, read from Water Data Online. The level of "
"the lake itself comes from the SWOT satellite at Belt Bay. Each is shown on its own page; here they are put "
"on the same time axis, which is the only way to see the delay between them.",
]),
("How long the water takes", "rl-lag", [
"The figures below compare the three series and look for the delay that best lines them up. It is a "
"first-order calculation: it describes a coincidence in time, not a proven cause, and it needs a long "
"enough overlap before it says anything at all. The daily rainfall series grows with each update, so this "
"page becomes more useful the longer the site runs.",
'<div id="travel-live" class="travel-live"></div>',
]),
("The 2025 flood, step by step", "rl-2025", [
"The 2025 flood is the best documented sequence the basin has, and it shows how long each stage takes. It "
"began with two rainfall episodes. The first, in February, came from the monsoon trough and tropical lows "
"over northern Queensland. The second and decisive one fell between 22 and 31 March, when a slow-moving "
"trough drew tropical moisture inland: daily totals of 50 to 200&nbsp;mm were recorded across much of western "
"Queensland, parts of the Channel Country exceeded their annual average of 300 to 400&nbsp;mm in four days, "
"and the highest four-day total reached 633&nbsp;mm at Sunbury, against an annual average of 379&nbsp;mm. For "
"much of south-western Queensland it was the wettest March on record {c:bom2025}.",
"The water then took two months to cross the basin. Satellite imagery gives an apparent propagation of 20 to "
"30&nbsp;km a day between late March and late April, falling to 13 to 17&nbsp;km a day when averaged from "
"mid-February, the difference measuring how much the flood is delayed by the country it crosses "
"{c:faraon2026}. On the Cooper, the same event produced the highest discharge ever recorded, 814&nbsp;GL a "
"day, on a floodplain up to 55&nbsp;km wide {c:rai2026b}.",
"The first wave reached the lake on 29 April 2025, down the Warburton, about two months after the March "
"rain. Some 20&nbsp;km upstream of the lake bed the flow divided in two: the Warburton Groove to the west, "
"which stayed confined to the centre of its channel and advanced at about 0.1&nbsp;m per second, and the "
"Kalaweerina Groove to the east, which spread directly onto the lake bed, peaked some ten days later and "
"advanced at about half that speed. A first-order partition of roughly three quarters to one quarter between "
"the two follows from their propagation {c:faraon2026}.",
"Cooper Creek began flowing into the lake around 28 June, two months after the Warburton and three after the "
"rain that fed it, and its sediment plume built up steadily rather than arriving as a surge {c:faraon2026}. "
"Once in the lake, the water stopped behaving like a river: under moderate westerly winds the waterline moved "
"500 to 1,000&nbsp;m eastward in a single day, which the bathymetry converts into about 30&nbsp;cm of set-down "
"in the west and 40&nbsp;cm of set-up in the east {c:faraon2026}.",
"The lake then dried from September 2025 to January 2026. Belt Bay and Madigan Gulf alternated between "
"connection and separation during November before parting for good around the 20th, after which their waters "
"diverged in colour and salinity {c:faraon2026}. Counted from the March rain to that separation, the whole "
"passage of one flood through the basin took some eight months.",
]),
]

if __name__ == "__main__":
    js, words, refs = refbuild.build(
        REFS, SECTIONS, var="RAIN_TO_LAKE_HTML", eyebrow="Catchment",
        title="From rain to lake",
        acknowledgement=("Kati Thanda&ndash;Lake Eyre lies on Arabana country. We acknowledge "
                         "the Arabana people as its Traditional Owners."),
        section_prefix="rl-", ref_prefix="rlref-",
        intro_comment="Temps de parcours de l'eau, construit par tools/build_rain_to_lake.py")
    open("frontend/rain_to_lake.js", "w", encoding="utf-8").write(js)
    print(f"rain_to_lake.js : {words} mots, {refs} références, toutes citées")
