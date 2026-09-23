#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/catchment.js, la partie Catchment du site.

Le bassin du lac Eyre : son etendue, ses rivieres, ses zones humides et
leur protection. Les references deja verifiees pour Natural History sont
lues a la source (refbuild.shared_refs) au lieu d'etre recopiees.

    python tools/build_catchment.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refbuild import build, shared_refs  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "frontend" / "catchment.js"

REFS = {
    "alec": ("ALEC n.d.", "the Arid Lands Environment Centre (n.d.)",
        "Arid Lands Environment Centre (n.d.) Lake Eyre Basin Intergovernmental Agreement.",
        "https://www.alec.org.au/lake_eyre_basin_intergovernmental_agreement"),
    "dcceew": ("DCCEEW 2023", "DCCEEW (2023)",
        "Department of Climate Change, Energy, the Environment and Water (2023) Lake Eyre Basin Intergovernmental Agreement.",
        "https://www.dcceew.gov.au/water/policy/national/lake-eyre-basin/agreement"),
    "dewagreement": ("DEW 2025", "DEW (2025)",
        "Department for Environment and Water, South Australia (2025) Lake Eyre Basin Intergovernmental Agreement.",
        "https://www.environment.sa.gov.au/topics/water-and-river-murray/legislation-projects-plans-and-security/legislation-and-policies/lake-eyre-basin-intergovernmental-agreement"),
    "kingsford2023": ("Kingsford and Walburn 2023", "Kingsford and Walburn (2023)",
        "Kingsford, R.T. and Walburn, A.J.D. (2023) Oil and gas exploration and development in the Lake Eyre Basin: distribution and consequences for rivers and wetlands, including the Coongie Lakes Ramsar Site. <i>Marine and Freshwater Research</i> 74, 200&ndash;219.",
        "https://doi.org/10.1071/MF22063"),
    "qld2019": ("Queensland Government 2019", "the Queensland Government (2019)",
        "Queensland Government (2019) Ministerial media statement on protection of the Lake Eyre Basin, 20 December 2019.",
        "https://statements.qld.gov.au/statements/89116"),
    "qldparl2023": ("Queensland Parliament 2023", "Queensland Parliament (2023)",
        "Queensland Parliament (2023) Question on Notice No. 1366, asked 26 October 2023: the Lake Eyre Basin Traditional Owner Alliance.",
        "https://documents.parliament.qld.gov.au/tableoffice/questionsanswers/2023/1366-2023.pdf"),
    "review1": ("DCCEEW n.d.a", "DCCEEW (n.d.a)",
        "Department of Climate Change, Energy, the Environment and Water (n.d.a) Review of the Lake Eyre Basin Intergovernmental Agreement: final report.",
        "https://www.dcceew.gov.au/sites/default/files/documents/final-review-leb-intergovernmental-agreement.pdf"),
    "review2": ("DCCEEW n.d.b", "DCCEEW (n.d.b)",
        "Department of Climate Change, Energy, the Environment and Water (n.d.b) The second review of the Lake Eyre Basin Intergovernmental Agreement.",
        "https://www.dcceew.gov.au/sites/default/files/sitecollectiondocuments/water/national/2nd-review-leb-intergovernmental-agreement.pdf"),
    "saal": ("Landscape SA 2021", "Landscape South Australia (2021)",
        "Landscape South Australia, SA Arid Lands (2021) Surface water.",
        "https://www.landscape.sa.gov.au/saal/water/managing-water-resources/surface-water"),
}
REFS.update(shared_refs(["habeck2014", "kotwicki1986", "costelloe2003",
                         "knighton1994", "rai2026b"]))
REFS.update(shared_refs(["kingsford1999"], source="build_fauna_flora.py"))

MAP = """<figure class="plate catchment-plate">
<div id="ct-map" class="catchment-map" role="img"
     aria-label="Map of the Lake Eyre Basin showing the places named on this page"></div>
<figcaption>Places named on this page, on a topographic base map where the rivers of
the basin can be followed. Locations are approximate.</figcaption>
</figure>"""

SECTIONS = [
("The basin", "ct-basin", [
"Kati Thanda is the end point of a river system that covers 1.2 million square kilometres and ranks among the largest internally draining systems in the world {c:review2}. The basin takes in large parts of Queensland, South Australia and the Northern Territory and a small part of western New South Wales, and around 60,000 people live and work within it {c:review2,kingsford2023}. Much of it overlies the Great Artesian Basin, and at peak flow the two systems together hold more than a quarter of Australia&rsquo;s fresh water {c:review2}.",
"Water reaches the lake by two great river systems from the north-east, the Georgina, Diamantina and Warburton, and the Thomson, Barcoo and Cooper, and by smaller rivers such as the Neales and the Macumba from the west {c:habeck2014}; the Finke and Todd rise in the Northern Territory {c:alec}. Most flows never reach the lake {c:alec}, and of those that do, the Diamantina, continuing as the Warburton, contributes the most {c:kotwicki1986}.",
MAP,
"{fig:basin-map|The Lake Eyre Basin and its main rivers, from the Queensland headwaters to the lake.}",
]),
("Rivers of the Channel Country", "ct-rivers", [
"Flows on the Georgina, Diamantina and Cooper are highly variable and unpredictable, their gradients very low and their losses downstream high {c:review1}. The Diamantina falls by only about 2.7&nbsp;&times;&nbsp;10<sup>&minus;4</sup> {c:costelloe2003}, and on Cooper Creek, once flow passes a threshold of about a quarter of the flow duration, transmission losses take more than three quarters of it {c:knighton1994}. In large floods the water leaves its channels for floodplains that can spread more than 60&nbsp;km wide {c:kingsford2023}.",
"The early months of 2025 brought the highest flood ever recorded on Cooper Creek, surpassing 1974 with a peak discharge of 814&nbsp;GL a day and a floodplain up to 55&nbsp;km wide {c:rai2026b}. Gauges are few in such country. On the Cooper, flows are measured at Nappa Merrie, station 003103A, near the Queensland border {c:kingsford2023}, and SWOT satellite altimetry has been assessed as a way to follow the 2025 flood along the river {c:rai2026b}.",
"{fig:channel-country-dry|The Channel Country in September 2024, dry: the channels show only as darker threads across the plains, the same country that carried the 2025 flood.}",
"{fig:cooper-waterhole|A waterhole on Cooper Creek between floods, where water persists long after the channels have stopped flowing.}",
]),
("Wetlands and booms", "ct-wetlands", [
"When floods arrive, the lakes, waterholes and wetlands of the far north of South Australia fill, plants regenerate, and waterbirds and fish breed in large numbers {c:saal}; on Cooper Creek, the size and timing of flows set these booms and the busts that follow {c:kingsford1999}. Between floods, waterholes and the upper floodplains become refuges for desert life {c:alec}. The basin holds 33 wetlands of national importance {c:kingsford2023}.",
"The Coongie Lakes, on the lower Cooper, were listed in 1987 as a Ramsar wetland of international importance. The site covers 21,889&nbsp;km&sup2;, of which 4,494&nbsp;km&sup2; is floodplain {c:kingsford2023}, and it includes the Malkumba&ndash;Coongie Lakes National Park {c:review2}.",
"{fig:coongie-lakes|The Coongie Lakes on the lower Cooper, listed in 1987 as a Ramsar wetland of international importance.}",
]),
("Free-flowing rivers", "ct-agreement", [
"The rivers of the basin remain largely unregulated, with no major dams and only small diversions for irrigation, which places them among the few free-flowing river systems left in the world {c:kingsford2023}. A proposal to irrigate cotton on Cooper Creek, and concern about what it would do to the flows reaching the Coongie Lakes, helped bring the Australian, Queensland and South Australian governments to commit to protecting the natural variability of the rivers {c:kingsford2023}.",
"The Lake Eyre Basin Intergovernmental Agreement they signed in 2000, joined by the Northern Territory in 2004, first applied to the Cooper Creek system, with the Thomson and Barcoo, and to the Georgina and Diamantina in Queensland and South Australia. It now also covers the Hay, Neales, Finke, Georgina and Todd catchments in the Territory and the Finke, Hay, Neales and Douglas Creek catchments in South Australia {c:dewagreement}. Its purpose is to avoid adverse impacts across borders so far as reasonably practicable, through a Ministerial Forum advised by a Community Advisory Committee and a Scientific Advisory Panel {c:dcceew}, and the Lake Eyre Basin Rivers Assessment follows the condition of its rivers, floodplains and wetlands {c:saal}.",
"Climate change, petroleum and mineral exploration and grazing all bear on the basin {c:alec}. Its floodplains carry 831 oil and gas wells, almost all of them along the Cooper, and within the Coongie Lakes Ramsar site the number of wells rose fivefold after its listing, from 233 to 1,236 {c:kingsford2023}. In Queensland, Traditional Owners from sixteen nations are represented in the Lake Eyre Basin Traditional Owner Alliance, formed with government support to give them an active role in decisions on the basin {c:qldparl2023,qld2019}. The <a href=\"#culture\">Aboriginal culture</a> part of this site names the peoples of the basin.",
]),
]

js, words, n = build(
    REFS, SECTIONS,
    var="CATCHMENT_HTML",
    eyebrow="Catchment",
    title="The rivers that feed the lake",
    acknowledgement=("The Lake Eyre Basin is the country of 71 Aboriginal language "
                     "groups. We pay our respects to their Elders past and present."),
    section_prefix="ct-", ref_prefix="ctref-",
    intro_comment=("Contenu de la partie Catchment, genere par "
                   "tools/build_catchment.py. Injecte par app.js a la premiere "
                   "ouverture."),
)
OUT.write_text(js, encoding="utf-8")
print(f"{OUT.name} : {words} mots, {n} références, toutes citées")
