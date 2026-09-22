#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/natural_history.js a partir d'un texte structure.

Pour modifier la partie Natural History : editer REFS et SECTIONS ci-dessous,
puis lancer  python tools/build_natural_history.py

Chaque citation est une cle : {c:a,b} donne une citation entre
parentheses, {n:a} une citation narrative. Une cle inconnue fait echouer
la construction, ce qui interdit toute reference inventee ou orpheline.
"""

import html
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "natural_history.js"

# cle : (forme courte, forme narrative, reference complete, lien)
REFS = {
    "baxter2003": ("Baxter 2003", "Baxter (2003)",
        "Baxter, C.I. (2003) Banded stilt <i>Cladorhynchus leucocephalus</i> breeding at Lake Eyre North in year 2000. <i>South Australian Ornithologist</i> 34, 33&ndash;56.", None),
    "birdlife2024": ("BirdLife International 2024", "BirdLife International (2024)",
        "BirdLife International (2024) Important Bird Area factsheet: Lake Eyre (Australia).",
        "https://datazone.birdlife.org/site/factsheet/lake-eyre-iba-australia"),
    "bonython1989": ("Bonython and Fraser 1989", "Bonython and Fraser (1989)",
        "Bonython, C.W. and Fraser, A.S. (eds) (1989) <i>The Great Filling of Lake Eyre in 1974</i>. Royal Geographical Society of Australasia, Adelaide.", None),
    "braysher1976": ("Braysher 1976", "Braysher (1976)",
        "Braysher, M.L. (1976) The excretion of hyperosmotic urine and other aspects of the electrolyte balance of the lizard <i>Amphibolurus maculosus</i>. <i>Comparative Biochemistry and Physiology</i> 54A, 341&ndash;345.", None),
    "bye1978": ("Bye et al. 1978", "Bye et al. (1978)",
        "Bye, J., Dillon, P., Vanderberg, C. and Will, G. (1978) Bathymetry of Lake Eyre. <i>Transactions of the Royal Society of South Australia</i> 102, 85&ndash;89.", None),
    "cohen2011": ("Cohen et al. 2011", "Cohen et al. (2011)",
        "Cohen, T.J., Nanson, G.C., Jansen, J.D. et al. (2011) Continental aridification and the vanishing of Australia&rsquo;s megalakes. <i>Geology</i> 39, 167&ndash;170.", None),
    "cohen2018": ("Cohen et al. 2018", "Cohen et al. (2018)",
        "Cohen, T.J., Meyer, M.C. and May, J.-H. (2018) Identifying extreme pluvials in the last millennia using optical dating of single grains of quartz from shorelines on Australia&rsquo;s largest lake. <i>The Holocene</i>.",
        "https://doi.org/10.1177/0959683617715700"),
    "costelloe2003": ("Costelloe et al. 2003", "Costelloe et al. (2003)",
        "Costelloe, J.F., Grayson, R.B., Argent, R.M. and McMahon, T.A. (2003) Modelling the flow regime of an arid zone floodplain river, Diamantina River, Australia. <i>Environmental Modelling &amp; Software</i> 18, 693&ndash;703.", None),
    "croke1999": ("Croke et al. 1999", "Croke et al. (1999)",
        "Croke, J.C., Magee, J.W. and Wallensky, E.P. (1999) The role of the Australian monsoon in the western catchment of Lake Eyre, central Australia, during the last interglacial. <i>Quaternary International</i> 57&ndash;58, 71&ndash;80.", None),
    "devogel2004": ("DeVogel et al. 2004", "DeVogel et al. (2004)",
        "DeVogel, S.B., Magee, J.W., Manley, W.F. and Miller, G.H. (2004) A GIS-based reconstruction of late Quaternary paleohydrology: Lake Eyre, arid central Australia. <i>Palaeogeography, Palaeoclimatology, Palaeoecology</i> 204, 1&ndash;13.", None),
    "dewpark": ("DEW n.d.a", "DEW (n.d.a)",
        "Department for Environment and Water, South Australia (n.d.a) Kati Thanda-Lake Eyre National Park. Park information.",
        "https://www.environment.sa.gov.au/parks/Find_a_Park/Browse_by_region/flinders-ranges-outback/kati-thanda-lake-eyre-national-park"),
    "dewsprings": ("DEW n.d.b", "DEW (n.d.b)",
        "Department for Environment and Water, South Australia (n.d.b) Wabma Kadarbu Mound Springs Conservation Park. Park information.",
        "https://www.parks.sa.gov.au/parks/wabma-kadarbu-mound-springs-conservation-park"),
    "dew2018": ("DEW 2018", "DEW (2018)",
        "Department for Environment and Water, South Australia (2018) Visit the mound springs. <i>Good Living</i>.",
        "https://environment.sa.gov.au/goodliving/posts/2018/05/visit-mound-springs"),
    "dodd2012": ("<i>Dodd v State of South Australia</i> [2012] FCA 519", "<i>Dodd v State of South Australia</i> [2012] FCA 519",
        "<i>Dodd v State of South Australia</i> [2012] FCA 519. Federal Court of Australia, consent determination of native title, 22 May 2012.", None),
    "doughty2007": ("Doughty et al. 2007", "Doughty et al. (2007)",
        "Doughty, P., Maryan, B., Melville, J. and Austin, J. (2007) A new species of <i>Ctenophorus</i> (Lacertilia: Agamidae) from Lake Disappointment, Western Australia. <i>Herpetologica</i> 63, 72&ndash;86.", None),
    "dulhunty1982": ("Dulhunty 1982", "Dulhunty (1982)",
        "Dulhunty, J.A. (1982) Holocene sedimentary environments in Lake Eyre, South Australia. <i>Journal of the Geological Society of Australia</i> 29, 437&ndash;442.", None),
    "evans2024": ("Evans et al. 2024", "Evans et al. (2024)",
        "Evans, T.J., Bishop, C., Symington, N.J., Halas, L., Hansen, J.W.H., Norton, C.J., Hannaford, C. and Lewis, S.J. (2024) <i>Cenozoic geology, hydrogeology, and groundwater systems: Kati Thanda&ndash;Lake Eyre Basin</i>. Record 2024/05, Geoscience Australia, Canberra.",
        "https://doi.org/10.26186/147422"),
    "fasullo2013": ("Fasullo et al. 2013", "Fasullo et al. (2013)",
        "Fasullo, J.T., Boening, C., Landerer, F.W. and Nerem, R.S. (2013) Australia&rsquo;s unique influence on global sea level in 2010&ndash;2011. <i>Geophysical Research Letters</i> 40, 4368&ndash;4373.", None),
    "gssa1962": ("Geological Survey of South Australia 1962", "the Geological Survey of South Australia (1962)",
        "Geological Survey of South Australia (1962) Investigations of Lake Eyre. Part 1: the sediments of the Lake Eyre Basin, evaporites and brines, their constitution and age. Report Book 54/00153.",
        "https://catalog.sarig.sa.gov.au/document/rb5400153"),
    "habeck2014": ("Habeck-Fardy and Nanson 2014", "Habeck-Fardy and Nanson (2014)",
        "Habeck-Fardy, A. and Nanson, G.C. (2014) Environmental character and history of the Lake Eyre Basin, one seventh of the Australian continent. <i>Earth-Science Reviews</i> 132, 39&ndash;66.", None),
    "keppel2013": ("Keppel et al. 2013", "Keppel et al. (2013)",
        "Keppel, M., Karlstrom, K., Love, A., Priestley, S., Wohling, D. and De Ritter, S. (eds) (2013) <i>Hydrogeological Framework of the Western Great Artesian Basin</i>, Volume 1. National Water Commission, Canberra.", None),
    "kingsford1993": ("Kingsford and Porter 1993", "Kingsford and Porter (1993)",
        "Kingsford, R.T. and Porter, J.L. (1993) Waterbirds of Lake Eyre, Australia. <i>Biological Conservation</i> 65, 141&ndash;151.", None),
    "kingsford1999": ("Kingsford et al. 1999", "Kingsford et al. (1999)",
        "Kingsford, R.T., Curtin, A.L. and Porter, J. (1999) Water flows on Cooper Creek in arid Australia determine &lsquo;boom&rsquo; and &lsquo;bust&rsquo; periods for waterbirds. <i>Biological Conservation</i> 88, 231&ndash;248.", None),
    "knighton1994": ("Knighton and Nanson 1994", "Knighton and Nanson (1994)",
        "Knighton, A.D. and Nanson, G.C. (1994) Flow transmission along an arid zone anastomosing river, Cooper Creek, Australia. <i>Hydrological Processes</i> 8, 137&ndash;154.", None),
    "kotwicki1986": ("Kotwicki 1986", "Kotwicki (1986)",
        "Kotwicki, V. (1986) <i>Floods of Lake Eyre</i>. Engineering and Water Supply Department, Adelaide.", None),
    "kotwicki1991": ("Kotwicki and Isdale 1991", "Kotwicki and Isdale (1991)",
        "Kotwicki, V. and Isdale, P. (1991) Hydrology of Lake Eyre, Australia: El Ni&ntilde;o link. <i>Palaeogeography, Palaeoclimatology, Palaeoecology</i> 84, 87&ndash;98.", None),
    "kotwicki1995": ("Kotwicki and Kundzewicz 1995", "Kotwicki and Kundzewicz (1995)",
        "Kotwicki, V. and Kundzewicz, Z.W. (1995) Hydrological uncertainty: floods of Lake Eyre. In: Kundzewicz, Z.W. (ed.) <i>New Uncertainty Concepts in Hydrology and Water Resources</i>. Cambridge University Press, Cambridge.", None),
    "leycboat": ("LEYC 2012", "the Lake Eyre Yacht Club (2012)",
        "Lake Eyre Yacht Club (2012) Boating history: sailing a dry lake, shipwreck on a wet lake. Chronology compiled from published sources and first-person accounts, updated 1 June 2012.",
        "https://lakeeyreyc.com/boathist.html"),
    "leychome": ("LEYC n.d.", "the Lake Eyre Yacht Club (n.d.)",
        "Lake Eyre Yacht Club (n.d.) Home page: foundation and aims of the club.",
        "https://lakeeyreyc.com/home.html"),
    "leon2012": ("Leon and Cohen 2012", "Leon and Cohen (2012)",
        "Leon, J.X. and Cohen, T.J. (2012) An improved bathymetric model for the modern and palaeo Lake Eyre. <i>Geomorphology</i> 173&ndash;174, 69&ndash;79.", None),
    "magee2004": ("Magee et al. 2004", "Magee et al. (2004)",
        "Magee, J.W., Miller, G.H., Spooner, N.A. and Questiaux, D. (2004) Continuous 150 k.y. monsoon record from Lake Eyre, Australia: insolation-forcing implications and unexpected Holocene failure. <i>Geology</i> 32, 885&ndash;888.", None),
    "mitchell1948": ("Mitchell 1948", "Mitchell (1948)",
        "Mitchell, F.J. (1948) A revision of the lacertilian genus <i>Tympanocryptis</i>. <i>Records of the South Australian Museum</i> 9, 57&ndash;86.", None),
    "mitchell1973": ("Mitchell 1973", "Mitchell (1973)",
        "Mitchell, F.J. (1973) Studies on the ecology of the agamid lizard <i>Amphibolurus maculosus</i> (Mitchell). <i>Transactions of the Royal Society of South Australia</i> 97, 47&ndash;76.", None),
    "nntt2012": ("NNTT 2012", "the National Native Title Tribunal (2012)",
        "National Native Title Tribunal (2012) Arabana native title claim resolved in South Australia. News release, 22 May 2012.",
        "https://www.nntt.gov.au/News-and-Publications/latest-news/Pages/ArabananativetitleclaimresolvedinSouthAustralia.aspx"),
    "nvis": ("NVIS MVG 22", "the NVIS fact sheet for Major Vegetation Group 22",
        "Australian Government (n.d.) National Vegetation Information System, Major Vegetation Group 22: chenopod shrublands, samphire shrublands and forblands. Fact sheet.",
        "https://www.agriculture.gov.au/sites/default/files/documents/mvg22-nvis-chenopod-shrublands-sampire-shrublands-and-forblands.pdf"),
    "pedler2014": ("Pedler et al. 2014", "Pedler et al. (2014)",
        "Pedler, R.D., Ribot, R.F.H. and Bennett, A.T.D. (2014) Extreme nomadism in desert waterbirds: flights of the banded stilt. <i>Biology Letters</i> 10, 20140547.", None),
    "pedler2014c": ("Pedler 2014", "Pedler (2014)",
        "Pedler, R. (2014) Banded stilts fly hundreds of kilometres to lay eggs that are over 50% of their body mass. <i>The Conversation</i>.",
        "https://theconversation.com/banded-stilts-fly-hundreds-of-kilometres-to-lay-eggs-that-are-over-50-of-their-body-mass-85447"),
    "ponder1989": ("Ponder et al. 1989", "Ponder et al. (1989)",
        "Ponder, W.F., Hershler, R. and Jenkins, B. (1989) An endemic radiation of hydrobiid snails from artesian springs in northern South Australia: their taxonomy, physiology, distribution and anatomy. <i>Malacologia</i> 31, 1&ndash;140.", None),
    "poulter2014": ("Poulter et al. 2014", "Poulter et al. (2014)",
        "Poulter, B., Frank, D., Ciais, P. et al. (2014) Contribution of semi-arid ecosystems to interannual variability of the global carbon cycle. <i>Nature</i> 509, 600&ndash;603.", None),
    "rai2026a": ("Rai et al. 2026a", "Rai et al. (2026a)",
        "Rai, A.K., Cohen, T.J., Armon, M. and Marx, S.K. (2026a) Volumetric analysis of a playa lake using SWOT data: an improved understanding of the inflows to Kati Thanda-Lake Eyre. <i>Journal of Hydrology</i> 676, 135652.",
        "https://doi.org/10.1016/j.jhydrol.2026.135652"),
    "rai2026b": ("Rai et al. 2026b", "Rai et al. (2026b)",
        "Rai, A.K., Cohen, T.J., Armon, M. and Marx, S.K. (2026b) SWOT satellite assessment for monitoring the extreme 2025 floods in Australia&rsquo;s inland Channel Country. <i>Environmental Research Letters</i> 21, 064013.",
        "https://doi.org/10.1088/1748-9326/ae530f"),
    "satc": ("SATC n.d.", "the South Australian Tourism Commission (n.d.)",
        "South Australian Tourism Commission (n.d.) Kati Thanda-Lake Eyre National Park.",
        "https://southaustralia.com/products/flinders-ranges-and-outback/attraction/kati-thandalake-eyre-national-park"),
    "thompson2018": ("Thompson and Bray 2018", "Thompson and Bray (2018)",
        "Thompson, V.J. and Bray, D.J. (2018) <i>Craterocephalus eyresii</i>. <i>Fishes of Australia</i>.",
        "https://fishesofaustralia.net.au/home/species/4634"),
    "ummenhofer2015": ("Ummenhofer et al. 2015", "Ummenhofer et al. (2015)",
        "Ummenhofer, C.C., Sen Gupta, A., England, M.H., Taschetto, A.S., Briggs, P.R. and Raupach, M.R. (2015) How did ocean warming affect Australian rainfall extremes during the 2010/2011 La Ni&ntilde;a event? <i>Geophysical Research Letters</i> 42, 9942&ndash;9951.", None),
    "wager2000": ("Wager and Unmack 2000", "Wager and Unmack (2000)",
        "Wager, R. and Unmack, P.J. (2000) <i>Fishes of the Lake Eyre Catchment of Central Australia</i>. Department of Primary Industries and Queensland Fisheries Service, Brisbane.", None),
    "waterman1992": ("Waterman and Read 1992", "Waterman and Read (1992)",
        "Waterman, M.H. and Read, J.L. (1992) Breeding success of the Australian pelican (<i>Pelecanus conspicillatus</i>) on Lake Eyre South in 1990. <i>Corella</i> 16, 123&ndash;126.", None),
}

# Titre, identifiant, paragraphes. Aucun tiret cadratin ni tiret espace
# comme ponctuation : les en-dash ne servent qu'aux intervalles et aux
# noms composes.
SECTIONS = [
("The lake", "nh-lake", [
"Kati Thanda&ndash;Lake Eyre occupies the lowest ground on the Australian continent, some 700&nbsp;km north of Adelaide, where the floor of Belt Bay lies about 15.2&nbsp;m below sea level {c:dewpark}. It is the terminal lake of the Lake Eyre Basin, an internally draining catchment of about 1.14&nbsp;million km&sup2; that gathers water from Queensland, the Northern Territory, New South Wales and South Australia {c:kotwicki1986,evans2024}. Lake Eyre North, some 144&nbsp;km long and 77&nbsp;km wide, joins Lake Eyre South, 64&nbsp;km by 24&nbsp;km, through the narrow Goyder Channel, and together the two cover about 9,700&nbsp;km&sup2; when water reaches their shores {c:dewpark,rai2026a}.",
"For most of any decade the lake is a white plain of salt, reached by floodwater on average once every eight years yet filled to capacity only three times in the past 160 years {c:dewpark}. Each filling turns a salt desert into one of the largest and most productive wetlands on the continent for as long as the water lasts, and it is this alternation, rather than any settled state, that defines the lake: its geology, its hydrology and its living communities are all organised around rare, large and unpredictable floods.",
"The dual name, adopted in 2012, joins the Arabana name Kati Thanda to the one given in honour of Edward John Eyre, who reached the region in 1840. The sections that follow gather what the published literature records of the lake&rsquo;s country and people, its geology and deep history, its water and climate, and the plants and animals that live with its cycles of flood and drought. The Observatory, the second half of this site, follows the lake as it is now.",
]),
("Country and people", "nh-country", [
"Kati Thanda lies on Arabana country, and on 22&nbsp;May 2012, sitting on country at Finniss Springs west of Marree, the Federal Court recognised the native title of the Arabana people over some 68,823&nbsp;km&sup2; of northern South Australia, an area that takes in the lake, the Wabma Kadarbu mound springs and the towns of Marree and William Creek {c:dodd2012,nntt2012}. The claim had been lodged in 1998, and the determination recognised non-exclusive rights to access and live on the land, to camp, and to hunt and fish. Kati Thanda&ndash;Lake Eyre National Park is managed in partnership with the Arabana and Dieri peoples, and recreational access to the lake bed is not permitted {c:satc}. The <a href=\"#culture\">Aboriginal Culture</a> part of this site names the nations around the lake and across its basin.",
"Knowledge of the lake&rsquo;s stories belongs to Arabana people, part of it restricted to initiated people, and it is not reproduced here; the Arabana Aboriginal Corporation is the proper place to begin for anyone wishing to learn more. Some Arabana place names are in public use, and the Department for Environment and Water gives them at the mound springs west of Lake Eyre South, where Thirrka (Blanche Cup) and Pirdali-nha (The Bubbler) rise beside Wabma Kadarbu, an extinct spring mound whose name means &lsquo;snake&rsquo;s head&rsquo; and which is central to the Arabana creation story for the site {c:dewsprings}.",
"European interest in the lake was long bound up with the idea of an inland sea, which explorers of the early nineteenth century set out to find {c:cohen2018}; Charles Sturt hauled a whaleboat on a dray in 1844&ndash;1846 and abandoned it near Depot Glen {c:leycboat}. Water in this country repeatedly outran those who came to meet it. In 1857 the colonial government sent the Surveyor-General with a flat-bottomed punt after George Goyder reported water at Lake Blanche, to the south-east, only for it to dry within four months, and in 1922 G.H. Halligan, having flown over Kati Thanda when it was a third full, returned by camel with a boat to find it dry {c:leycboat}.",
"Boats reached the lake in numbers only with the great filling of 1974, which brought the first north to south crossing, the first yacht and, in May 1976, a sailing regatta at Level Post Bay {c:leycboat}. The Lake Eyre Yacht Club, founded in April 2000, has since collected accounts of fillings and of boating on the lake {c:leychome,leycboat}. The hard salt crust served a very different purpose in 1964, when Donald Campbell drove Bluebird-Proteus CN7 across it on 17&nbsp;July to set a land speed record of 648.7&nbsp;km/h.",
]),
("Geology and landscape", "nh-geology", [
"Kati Thanda is the present depocentre of the Lake Eyre Basin, a Cenozoic sedimentary basin that drapes older rocks including the Mesozoic Eromanga and Palaeozoic Cooper basins {c:evans2024}. The focus of subsidence has migrated through the Cenozoic, from near the Queensland and Northern Territory border towards the southern Simpson Desert by the late Neogene and on to its present position beneath the lake, and the succession it left behind records a change from the wetter landscapes of the Palaeogene to the aridity of today {c:evans2024,habeck2014}.",
"The Palaeogene Eyre Formation, up to about 185&nbsp;m of fluvial sand that forms the basin&rsquo;s regional aquifer, is overlain by the broadly contemporaneous Namba and Etadunna formations of the Callabonna and Tirari sub-basins, up to 265&nbsp;m and 180&nbsp;m thick respectively, the Namba acting as a regional aquitard {c:evans2024}. Beneath the lake the modern sediments are remarkably thin, less than about 4.5&nbsp;m over the deflated floor, and rest directly on dolomite of the Etadunna Formation, which crops out east of the lake and carries a characteristic mammalian fauna {c:gssa1962}. Structures at or near the surface can be traced down into the underlying Eromanga and Cooper basins, and neotectonic features suggest that deformation continues to shape the basin {c:evans2024}.",
"The lake floor grades from about &minus;10&nbsp;m AHD in the far north to &minus;15&nbsp;m in the southern bays, some 110&nbsp;km away, and is broken by islands, inlets and peninsulas {c:leon2012,rai2026a}. {n:dulhunty1982} divided it into geomorphic zones that still frame its description: a northern saline playa, a slush zone where a thin skin of salt covers wet, gypsum-rich mud, and the deepest southern embayments of Belt Bay, Jackboot Bay and Madigan Gulf, where a hard halite crust can reach about half a metre in thickness. Because each filling dissolves and redeposits that salt, the lowest point of the lake is not fixed but shifts among these southern bays.",
"The lake also sits over the south-western margin of the Great Artesian Basin, whose confined sandstone aquifers carry water westward from recharge areas in Queensland. Where faults cut the confining clays, or where those clays thin, the pressurised water reaches the surface as springs, and along the western and southern margins of the lake minerals precipitated around their vents have built the low mounds that give the mound springs their name {c:keppel2013}.",
]),
("A lake through time", "nh-deep-time", [
"Around 125,000 years ago, during the Last Interglacial, Lake Eyre stood at about +10&nbsp;m AHD and, joined to the Frome and Gregory system to the south-east, covered more than 35,000&nbsp;km&sup2; and held some 430&nbsp;km&sup3; of water, more than fourteen times the 30&nbsp;km&sup3; of the deepest historical filling in 1974 {c:devogel2004}. Its raised shorelines show that the lake was perennial during several phases of stronger monsoon, around 125, 80, 65 and 40 thousand years ago, when the Cooper and the Diamantina supplied most of its inflow {c:magee2004,devogel2004,croke1999}.",
"Because the lake integrates rainfall over so much of the continent, its history reads as a record of the Australian monsoon, and the 150,000-year record assembled by {n:magee2004} ends in an unexpected failure of the monsoon to reach the basin during the Holocene. Lake Mega-Frome, the coalesced Frome, Blanche, Callabonna and Gregory lakes, connected with Lake Eyre for the last time between about 50,000 and 47,000 years ago; its disconnection marks a shift towards aridity that coincided with the arrival of people on the continent and the demise of the megafauna {c:cohen2011}.",
"Fillings on the scale of 1974 nonetheless belong to the lake&rsquo;s recent behaviour rather than to historical accident: shorelines at or near that level have been dated by single-grain luminescence to within the last decades to centuries, in the first, preliminary chronology of such events {c:cohen2018}.",
]),
("Water and climate", "nh-water", [
"Kati Thanda lies in the driest part of Australia, where rainfall averages little more than 120&nbsp;mm a year and varies greatly from one year to the next {c:keppel2013}. The basin&rsquo;s mean annual runoff, about 4&nbsp;km&sup3;, is the lowest of any major drainage basin in the world {c:kotwicki1995}, and almost all the water that reaches the lake has fallen far to the north, in the summer monsoon over Queensland.",
"That water travels by two great river systems from the north-east, the Georgina, Diamantina and Warburton, and the Thomson, Barcoo and Cooper, and by smaller rivers such as the Neales and the Macumba from the west {c:habeck2014}; the Diamantina, continuing as the Warburton, is the main contributor {c:kotwicki1986}. Gradients are extraordinarily low, about 2.7&nbsp;&times;&nbsp;10<sup>&minus;4</sup> on the Diamantina {c:costelloe2003}, and the rivers spread into anabranching channels, waterholes and floodplains where much of their flow is lost; on Cooper Creek, above a threshold of about a quarter of the flow duration, transmission losses exceed three quarters of the flow {c:knighton1994}. Rain that fell in Queensland may therefore take weeks or months to reach the lake, and much of it never arrives.",
"The rhythm of filling follows the tropical Pacific: {n:kotwicki1991} linked the historical inflows to the El Ni&ntilde;o&ndash;Southern Oscillation, large fillings coinciding with strong La Ni&ntilde;a years, and {n:kotwicki1986} identified 1891, 1906, 1941, 1949&ndash;1951, 1953, 1955&ndash;1959 and 1963 as significant filling years. The greatest historical filling came in 1974, Australia&rsquo;s wettest year on record {c:ummenhofer2015}, when the lake reached depths of about 6&nbsp;m and held some 30&nbsp;km&sup3; {c:bye1978,kotwicki1986,bonython1989,devogel2004}. That year the Goyder Channel carried water from the northern lake to the southern; in 1984 and 1989 local rain filled Lake Eyre South instead, which overflowed northward and filled Lake Eyre North to 3.5&nbsp;m and 3.0&nbsp;m, the first time Europeans had seen the channel run from south to north {c:leycboat}.",
"When the lake is deep its water is about as saline as the sea, but it dissolves the crust beneath it and concentrates as it evaporates, until the remaining brine reaches saturation. Such wet years matter well beyond the basin: the greening of Australia&rsquo;s semi-arid interior in 2011 made a measurable contribution to the global land carbon sink {c:poulter2014}, and the water stored inland that year briefly lowered global mean sea level {c:fasullo2013}.",
"The most recent fillings have been observed as never before: in 2024 the lake reached a maximum extent of about 910&nbsp;km&sup2;, a depth of 1.42&nbsp;m and a volume of 0.82&nbsp;km&sup3;, measured directly from SWOT satellite altimetry {c:rai2026a}. The extreme floods of early 2025, the largest in at least fifty years in the Lake Eyre Basin, produced the highest flood ever recorded on Cooper Creek, surpassing 1974 with a peak discharge of 814&nbsp;GL a day and a floodplain up to 55&nbsp;km wide {c:rai2026b}. The Observatory takes up the story from there.",
]),
("Plants", "nh-flora", [
"Plant life avoids the salt pan itself and gathers at its margins, on the surrounding plains and dunes, and around the springs: succulent samphires, the glassworts of the genus <i>Tecticornia</i>, fringe the salt lakes, while the clay and gibber plains beyond carry low chenopod shrublands of saltbush and bluebush, drought- and salt-tolerant shrubs of a family with a deep evolutionary history in Australia; their presence in the mid-Tertiary, when much of the continent was covered by rainforest, points to an ancient desert flora {c:nvis}.",
"Around the mound springs that scarcity gives way to permanent wetland. Their pools and outflows are ringed by green sedges {c:dewsprings}, oases in an arid landscape that support plants and invertebrates found nowhere else. When floodwater reaches the lake, the brine itself comes alive with microscopic algae, among them <i>Dunaliella salina</i>, whose carotenoid pigments can tint the most concentrated brines pink.",
]),
("Animals", "nh-fauna", [
"The Lake Eyre dragon, <i>Ctenophorus maculosus</i>, first described from Lake Eyre North {c:mitchell1948}, lives on and beneath the dry salt crust itself {c:doughty2007}, sheltering in cracks in the salt and feeding largely on ants. Its pale, blotched colouring matches the salt around it, and its physiology is tuned to heat and to the absence of free water, down to the excretion of highly concentrated urine {c:mitchell1973,braysher1976}.",
"Once the lake floods, its food web starts from dormant eggs: those of brine shrimp, <i>Parartemia</i>, lie in the crust for years or decades and hatch in their billions once wetted, and banded stilts, <i>Cladorhynchus leucocephalus</i>, respond within days, flying hundreds to thousands of kilometres from coastal wetlands to breed in dense colonies {c:pedler2014} and laying clutches that can exceed half the female&rsquo;s body mass {c:pedler2014c}. Silver gulls prey heavily on their eggs and chicks. In 2000, after gulls had destroyed two nesting attempts on Ibis Island in Lake Eyre North, a targeted control of the gulls allowed a third colony of some 20,000 nests to raise tens of thousands of young {c:baxter2003}.",
"The rivers bring freshwater fish with them, and while the water stays fresh, bony bream, the Lake Eyre Basin form of golden perch and several hardyheads live in the lake {c:wager2000}. The Lake Eyre hardyhead, <i>Craterocephalus eyresii</i>, tolerates salinities from fresh water to 110 parts per thousand, the widest range of any Australian fish {c:thompson2018}, yet as the lake shrank in 1975 an estimated twenty million died as the water grew saltier {c:wager2000}.",
"Those fish feed great breeding colonies of fish-eating birds, and in 1990 Australian pelicans nesting on three islands in Lake Eyre South laid an estimated 104,000 eggs and fledged up to 90,000 chicks {c:waterman1992}, among the most successful pelican breeding events recorded in Australia. When the lake holds water, silver gulls, red-necked avocets, banded stilts and gull-billed terns gather in their thousands {c:dewpark}, and aerial surveys have established the lake and its rivers as among the continent&rsquo;s most important, if intermittent, waterbird habitats, their boom and bust set by the timing of floods {c:kingsford1993,kingsford1999,birdlife2024}.",
"Across the Great Artesian Basin more than 90 species are found only in springs, over half of them in South Australia&rsquo;s mound springs {c:dew2018}, among them a radiation of tiny hydrobiid snails and crustaceans such as the isopod <i>Phreatomerus latipes</i> {c:ponder1989}. Each is confined to the permanent water of a few vents, which makes the springs as vulnerable as they are remarkable.",
]),
]

CITE = re.compile(r"\{([cn]):([a-z0-9,]+)\}")
used = set()


def link(key, text):
    if key not in REFS:
        sys.exit(f"Clé de citation inconnue : {key}")
    used.add(key)
    return f'<a class="cite" href="#ref-{key}">{text}</a>'


def render(par):
    def sub(m):
        kind, keys = m.group(1), m.group(2).split(",")
        if kind == "n":
            if len(keys) != 1:
                sys.exit("Une citation narrative ne prend qu'une clé")
            return link(keys[0], REFS[keys[0]][1] if keys[0] in REFS else keys[0])
        return "(" + "; ".join(link(k, REFS[k][0] if k in REFS else k)
                               for k in keys) + ")"
    return CITE.sub(sub, par)


# Garde-fou de style : pas de tiret comme ponctuation dans la prose
for title, _, pars in SECTIONS:
    for p in pars:
        plain = html.unescape(re.sub(r"<[^>]+>", "", CITE.sub("", p)))
        if "\u2014" in plain or " \u2013 " in plain or " - " in plain:
            sys.exit(f"Tiret de ponctuation dans « {title} » : {plain[:80]}")

toc = "".join(f'<li><a href="#{sid}">{t}</a></li>' for t, sid, _ in SECTIONS)
toc += '<li><a href="#nh-references">References</a></li>'

body = []
for title, sid, pars in SECTIONS:
    body.append(f'<section class="nh-section" id="{sid}"><h3>{title}</h3>')
    body.extend(f"<p>{render(p)}</p>" for p in pars)
    body.append("</section>")

unused = sorted(set(REFS) - used)
if unused:
    sys.exit(f"Références jamais citées : {unused}")


def sort_key(k):
    return re.sub(r"<[^>]+>", "", REFS[k][2]).lower()


refs_html = []
for k in sorted(REFS, key=sort_key):
    _, _, full, url = REFS[k]
    extra = (f' <a href="{url}" target="_blank" rel="noopener">'
             f'{html.escape(url.replace("https://", ""))}</a>') if url else ""
    refs_html.append(f'<li id="ref-{k}">{full}{extra}</li>')

page = f"""<article class="panel nh-article">
<div class="panel-head">
<p class="eyebrow">Natural history</p>
<h2>Kati Thanda&ndash;Lake Eyre</h2>
</div>
<div class="nh-layout">
<aside class="nh-toc" aria-label="Contents">
<p class="nh-toc-title">Contents</p>
<ol>{toc}</ol>
</aside>
<div class="nh-body prose-body">
<p class="nh-acknowledgement">Kati Thanda&ndash;Lake Eyre lies on the country of the Arabana people. We acknowledge the Arabana as the Traditional Owners of the lake and its surrounds, and pay our respects to their Elders past and present.</p>
{''.join(body)}
<section class="nh-section" id="nh-references"><h3>References</h3>
<ol class="nh-references">{''.join(refs_html)}</ol>
</section>
</div>
</div>
</article>"""

js = ("/* Contenu de la partie Natural History, genere a partir d'une source\n"
      " * structuree dont chaque citation est verifiee contre la liste des\n"
      " * references. Injecte par app.js a la premiere ouverture. */\n"
      f"const NATURAL_HISTORY_HTML = {json.dumps(page, ensure_ascii=False)};\n")
OUT.write_text(js, encoding="utf-8")

words = len(re.sub(r"<[^>]+>", " ", "".join(body)).split())
print(f"{OUT.name} : {len(SECTIONS)} sections, {words} mots, "
      f"{len(REFS)} références, toutes citées")
