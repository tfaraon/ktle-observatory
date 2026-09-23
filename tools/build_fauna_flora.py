#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/fauna_flora.js, page Plants and animals de la partie
Fauna and flora.

Ces deux sections viennent de Natural History, deplacees telles quelles.
Les references citees seulement ici ont demenage avec elles ; celles que
les deux pages partagent restent dans build_natural_history.py et sont
lues a la source (refbuild.shared_refs).

    python tools/build_fauna_flora.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refbuild import build, shared_refs  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "frontend" / "fauna_flora.js"

REFS = {
    "baxter2003": ("Baxter 2003", "Baxter (2003)",
        "Baxter, C.I. (2003) Banded stilt <i>Cladorhynchus leucocephalus</i> breeding at Lake Eyre North in year 2000. <i>South Australian Ornithologist</i> 34, 33&ndash;56.",
        None),
    "birdlife2024": ("BirdLife International 2024", "BirdLife International (2024)",
        "BirdLife International (2024) Important Bird Area factsheet: Lake Eyre (Australia).",
        "https://datazone.birdlife.org/site/factsheet/lake-eyre-iba-australia"),
    "braysher1976": ("Braysher 1976", "Braysher (1976)",
        "Braysher, M.L. (1976) The excretion of hyperosmotic urine and other aspects of the electrolyte balance of the lizard <i>Amphibolurus maculosus</i>. <i>Comparative Biochemistry and Physiology</i> 54A, 341&ndash;345.",
        None),
    "dew2018": ("DEW 2018", "DEW (2018)",
        "Department for Environment and Water, South Australia (2018) Visit the mound springs. <i>Good Living</i>.",
        "https://environment.sa.gov.au/goodliving/posts/2018/05/visit-mound-springs"),
    "doughty2007": ("Doughty et al. 2007", "Doughty et al. (2007)",
        "Doughty, P., Maryan, B., Melville, J. and Austin, J. (2007) A new species of <i>Ctenophorus</i> (Lacertilia: Agamidae) from Lake Disappointment, Western Australia. <i>Herpetologica</i> 63, 72&ndash;86.",
        None),
    "kingsford1993": ("Kingsford and Porter 1993", "Kingsford and Porter (1993)",
        "Kingsford, R.T. and Porter, J.L. (1993) Waterbirds of Lake Eyre, Australia. <i>Biological Conservation</i> 65, 141&ndash;151.",
        None),
    "kingsford1999": ("Kingsford et al. 1999", "Kingsford et al. (1999)",
        "Kingsford, R.T., Curtin, A.L. and Porter, J. (1999) Water flows on Cooper Creek in arid Australia determine &lsquo;boom&rsquo; and &lsquo;bust&rsquo; periods for waterbirds. <i>Biological Conservation</i> 88, 231&ndash;248.",
        None),
    "mitchell1948": ("Mitchell 1948", "Mitchell (1948)",
        "Mitchell, F.J. (1948) A revision of the lacertilian genus <i>Tympanocryptis</i>. <i>Records of the South Australian Museum</i> 9, 57&ndash;86.",
        None),
    "mitchell1973": ("Mitchell 1973", "Mitchell (1973)",
        "Mitchell, F.J. (1973) Studies on the ecology of the agamid lizard <i>Amphibolurus maculosus</i> (Mitchell). <i>Transactions of the Royal Society of South Australia</i> 97, 47&ndash;76.",
        None),
    "nvis": ("NVIS MVG 22", "the NVIS fact sheet for Major Vegetation Group 22",
        "Australian Government (n.d.) National Vegetation Information System, Major Vegetation Group 22: chenopod shrublands, samphire shrublands and forblands. Fact sheet.",
        "https://www.agriculture.gov.au/sites/default/files/documents/mvg22-nvis-chenopod-shrublands-sampire-shrublands-and-forblands.pdf"),
    "pedler2014": ("Pedler et al. 2014", "Pedler et al. (2014)",
        "Pedler, R.D., Ribot, R.F.H. and Bennett, A.T.D. (2014) Extreme nomadism in desert waterbirds: flights of the banded stilt. <i>Biology Letters</i> 10, 20140547.",
        None),
    "pedler2014c": ("Pedler 2014", "Pedler (2014)",
        "Pedler, R. (2014) Banded stilts fly hundreds of kilometres to lay eggs that are over 50% of their body mass. <i>The Conversation</i>.",
        "https://theconversation.com/banded-stilts-fly-hundreds-of-kilometres-to-lay-eggs-that-are-over-50-of-their-body-mass-85447"),
    "ponder1989": ("Ponder et al. 1989", "Ponder et al. (1989)",
        "Ponder, W.F., Hershler, R. and Jenkins, B. (1989) An endemic radiation of hydrobiid snails from artesian springs in northern South Australia: their taxonomy, physiology, distribution and anatomy. <i>Malacologia</i> 31, 1&ndash;140.",
        None),
    "thompson2018": ("Thompson and Bray 2018", "Thompson and Bray (2018)",
        "Thompson, V.J. and Bray, D.J. (2018) <i>Craterocephalus eyresii</i>. <i>Fishes of Australia</i>.",
        "https://fishesofaustralia.net.au/home/species/4634"),
    "wager2000": ("Wager and Unmack 2000", "Wager and Unmack (2000)",
        "Wager, R. and Unmack, P.J. (2000) <i>Fishes of the Lake Eyre Catchment of Central Australia</i>. Department of Primary Industries and Queensland Fisheries Service, Brisbane.",
        None),
    "waterman1992": ("Waterman and Read 1992", "Waterman and Read (1992)",
        "Waterman, M.H. and Read, J.L. (1992) Breeding success of the Australian pelican (<i>Pelecanus conspicillatus</i>) on Lake Eyre South in 1990. <i>Corella</i> 16, 123&ndash;126.",
        None),
    "badman1991b": ("Badman 1991b", "Badman (1991b)",
        "Badman, F.J. (1991b) Vegetation. In: Badman, F.J., Arnold, B.K. and Bell, S.L. (eds) <i>A Natural History of the Lake Eyre Region: A Visitor&rsquo;s Guide</i>, pp. 17&ndash;28. National Parks and Wildlife Service, Northern Consultative Committee, Port Augusta.",
        None),
    "badman1991c": ("Badman 1991c", "Badman (1991c)",
        "Badman, F.J. (1991c) Birds. In: Badman, F.J., Arnold, B.K. and Bell, S.L. (eds) <i>A Natural History of the Lake Eyre Region: A Visitor&rsquo;s Guide</i>, pp. 29&ndash;38. National Parks and Wildlife Service, Northern Consultative Committee, Port Augusta.",
        None),
    "kemper1991": ("Kemper and Read 1991", "Kemper and Read (1991)",
        "Kemper, C.M. and Read, J.L. (1991) Mammals. In: Badman, F.J., Arnold, B.K. and Bell, S.L. (eds) <i>A Natural History of the Lake Eyre Region: A Visitor&rsquo;s Guide</i>, pp. 39&ndash;43. National Parks and Wildlife Service, Northern Consultative Committee, Port Augusta.",
        None),
    "read1991": ("Read 1991", "Read (1991)",
        "Read, J.L. (1991) Reptiles and amphibians. In: Badman, F.J., Arnold, B.K. and Bell, S.L. (eds) <i>A Natural History of the Lake Eyre Region: A Visitor&rsquo;s Guide</i>, pp. 44&ndash;50. National Parks and Wildlife Service, Northern Consultative Committee, Port Augusta.",
        None),
}
REFS.update(shared_refs(["dewpark", "dewsprings"]))

SECTIONS = [
("Plants and algae", "ff-plants", [
"Plant life avoids the salt pan itself and gathers at its margins, on the surrounding plains and dunes, and around the springs: succulent samphires, the glassworts of the genus <i>Tecticornia</i>, fringe the salt lakes, while the clay and gibber plains beyond carry low chenopod shrublands of saltbush and bluebush, drought- and salt-tolerant shrubs of a family with a deep evolutionary history in Australia; their presence in the mid-Tertiary, when much of the continent was covered by rainforest, points to an ancient desert flora {c:nvis}.",
"More than 1,070 plant species, in 378 genera and 81 families, had been collected in the Lake Eyre botanic region by 1991, and the flora is dominated by the saltbush family, the daisies and the grasses {c:badman1991b}. On the gibber plains the most important shrubs are bladder saltbush, <i>Atriplex vesicaria</i>, and low bluebush, <i>Maireana astrotricha</i>, while black bluebush, <i>M. pyramidata</i>, though often dominant, usually marks degraded or poor soils; bladder saltbush lives for about a quarter of a century and low bluebush for about 75 years, and after good rains <i>Swainsona</i> peas can carpet the plains in purple or orange as far as the eye can see {c:badman1991b}.",
"{fig:gibber-plain|Gibber plain with its low chenopod shrubland, the vegetation that covers much of the country around the lake.}",
"On the dunefields, sandhill cane-grass, <i>Zygochloa paradoxa</i>, binds the unstable crests and is the preferred habitat of the Eyrean grasswren, while porcupine grass, <i>Triodia</i>, often wrongly called spinifex, grows in the swales; its resin was once widely used by Aboriginal people as an adhesive {c:badman1991b}. Along the watercourses, river red gums grow only in the upper reaches where salinity is lowest, and coolibahs line creeks and floodplains over much of the region but cannot survive the high salinity close to the lake {c:badman1991b}. In the flood-out areas grows nardoo, arid-adapted ferns of which five species occur in the region; their spore cases once formed an important part of the diet of Aboriginal people, collected by women and ground into a paste that was cooked as a kind of cake {c:badman1991b}.",
"Around the mound springs that scarcity gives way to permanent wetland. Their pools and outflows are ringed by green sedges {c:dewsprings}, oases in an arid landscape that support plants and invertebrates found nowhere else. When floodwater reaches the lake, the brine itself comes alive with microscopic algae, among them <i>Dunaliella salina</i>, whose carotenoid pigments can tint the most concentrated brines pink.",
"<div class=\"obs-block\" data-groups=\"Plantae\" data-name=\"plants\"></div>",
"{fig:samphire|Samphire, <i>Tecticornia</i>, the low succulent shrubland that fringes the salt lakes.}",
]),
("Invertebrates", "ff-invertebrates", [
"Once the lake floods, its food web starts from dormant eggs: those of brine shrimp, <i>Parartemia</i>, lie in the crust for years or decades and hatch in their billions once wetted {c:pedler2014}.",
"Across the Great Artesian Basin more than 90 species are found only in springs, over half of them in South Australia&rsquo;s mound springs {c:dew2018}, among them a radiation of tiny hydrobiid snails and crustaceans such as the isopod <i>Phreatomerus latipes</i> {c:ponder1989}. Each is confined to the permanent water of a few vents, which makes the springs as vulnerable as they are remarkable.",
"<div class=\"obs-block\" data-groups=\"Insecta,Arachnida,Mollusca,Animalia\" data-name=\"invertebrates\"></div>",
]),
("Fish", "ff-fish", [
"The rivers bring freshwater fish with them, and while the water stays fresh, bony bream, the Lake Eyre Basin form of golden perch and several hardyheads live in the lake {c:wager2000}. The Lake Eyre hardyhead, <i>Craterocephalus eyresii</i>, tolerates salinities from fresh water to 110 parts per thousand, the widest range of any Australian fish {c:thompson2018}, yet as the lake shrank in 1975 an estimated twenty million died as the water grew saltier {c:wager2000}.",
"<div class=\"obs-block\" data-groups=\"Actinopterygii\" data-name=\"fish\"></div>",
]),
("Frogs", "ff-frogs", [
"Although the deserts around the lake are usually very dry, three species of frog live there, and in places they are abundant {c:read1991}. The water-holding frog and the trilling frog spend most of their lives buried in clay up to 40&nbsp;cm deep, shielded from the sun and the heat inside a cocoon formed from their shed skins, which limits water loss while letting them breathe; after a heavy downpour they dig back to the surface, feed, find a mate and spawn before the temporary pools dry {c:read1991}. Few people see these gatherings, because the rains that bring them out also close the outback roads {c:read1991}. The desert tree frog shelters under rocks or logs near semi-permanent pools and is often seen around the homesteads of the Birdsville Track {c:read1991}.",
"<div class=\"obs-block\" data-groups=\"Amphibia\" data-name=\"frogs\"></div>",
]),
("Reptiles", "ff-reptiles", [
"The Lake Eyre dragon, <i>Ctenophorus maculosus</i>, first described from Lake Eyre North {c:mitchell1948}, lives on and beneath the dry salt crust itself {c:doughty2007}, sheltering in cracks in the salt and feeding largely on ants. Its pale, blotched colouring matches the salt around it, and its physiology is tuned to heat and to the absence of free water, down to the excretion of highly concentrated urine {c:mitchell1973,braysher1976}. In very hot or very cold weather it burrows into the moist mud beneath the crust {c:read1991}.",
"More than fifty species of reptiles live around the lake, from the perentie, Australia&rsquo;s largest lizard, to Grey&rsquo;s skink, among its smallest, and while no reptile or frog is known to have been lost from the region, rabbits, cats and foxes have harmed many {c:read1991}. Gould&rsquo;s goanna is one of the reptiles most often seen, from the dunes to the gibber plains, and central bearded dragons are common on the chenopod plains {c:read1991}.",
"<div class=\"obs-block\" data-groups=\"Reptilia\" data-name=\"reptiles\"></div>",
"{fig:lake-eyre-dragon|The Lake Eyre dragon, <i>Ctenophorus maculosus</i>, which lives on the salt crust itself.}",
]),
("Birds", "ff-birds", [
"Banded stilts, <i>Cladorhynchus leucocephalus</i>, respond within days to the hatching of brine shrimp, flying hundreds to thousands of kilometres from coastal wetlands to breed in dense colonies {c:pedler2014} and laying clutches that can exceed half the female&rsquo;s body mass {c:pedler2014c}. Silver gulls prey heavily on their eggs and chicks. In 2000, after gulls had destroyed two nesting attempts on Ibis Island in Lake Eyre North, a targeted control of the gulls allowed a third colony of some 20,000 nests to raise tens of thousands of young {c:baxter2003}.",
"The fish that the rivers bring feed great breeding colonies of fish-eating birds, and in 1990 Australian pelicans nesting on three islands in Lake Eyre South laid an estimated 104,000 eggs and fledged up to 90,000 chicks {c:waterman1992}, among the most successful pelican breeding events recorded in Australia. When the lake holds water, silver gulls, red-necked avocets, banded stilts and gull-billed terns gather in their thousands {c:dewpark}, and aerial surveys have established the lake and its rivers as among the continent&rsquo;s most important, if intermittent, waterbird habitats, their boom and bust set by the timing of floods {c:kingsford1993,kingsford1999,birdlife2024}.",
"By 1991, 230 bird species had been reliably recorded in the South Australian part of the basin, new ones, mostly migratory waders, were still being added, and the grass owl, grey grasswren and yellow chat had all been found in the Clifton Hills area since 1975 {c:badman1991c}. About half of these species feed on the ground and about half are nomadic, moving to wherever rain has brought better conditions and breeding only when conditions allow {c:badman1991c}. The source of the water decides which birds come: lakes filled by the rivers bring fish, and with them fish-eating birds, while lakes filled only by local rain hold few fish but abundant small crustaceans and insects, and draw waders instead {c:badman1991c}. The Eyrean grasswren, long thought extinct and later considered extremely rare, was by then known to be moderately common in the Simpson, Tirari and Strzelecki deserts, living far from any water on the moisture in its food {c:badman1991c}.",
"The birds reported around the lake over the last month are also mapped under <a href=\"#birds\">Bird sightings</a>, where you can submit your own.",
"<div class=\"obs-block\" data-groups=\"Aves\" data-name=\"birds\" data-ebird=\"true\"></div>",
"{fig:waterbird-colony|Waterbirds gathered on the flooded lake, the pulse of life that follows each filling.}",
]),
("Mammals", "ff-mammals", [
"The most striking feature of the region&rsquo;s mammals, in the words of {n:kemper1991}, is the &ldquo;epidemic of presumed extinctions&rdquo; of the past century: ten species observed by early explorers and naturalists no longer occur there, among them the desert rat-kangaroo, the crescent nailtail wallaby, the pig-footed bandicoot, both bilbies and the lesser stick-nest rat, while the burrowing bettong and the greater stick-nest rat survived in 1991 only as small populations on offshore islands. Introduced predators, rabbits, overgrazing, changed fire regimes and disease have all been blamed, and no single factor is thought to be responsible {c:kemper1991}.",
"After exceptional rain, native rodents can build up to great numbers, as the long-haired rat does in irruptions and as the spinifex hopping mouse did in 1990; along the Cooper and the Diamantina, water rats may move downstream towards the lake in floods {c:kemper1991,badman1991c}. House mice, which sometimes reach plague numbers, now form the basis of the diet of several native snakes and birds of prey {c:kemper1991}.",
"<div class=\"obs-block\" data-groups=\"Mammalia\" data-name=\"mammals\"></div>",
]),
]

if __name__ == "__main__":
    js, words, n = build(
        REFS, SECTIONS,
        var="FAUNA_FLORA_HTML",
        eyebrow="Fauna and flora",
        title="Plants and animals of the lake",
        acknowledgement=("Kati Thanda&ndash;Lake Eyre lies on Arabana country. We acknowledge "
                         "the Arabana as Traditional Owners and pay our respects to their "
                         "Elders past and present."),
        section_prefix="ff-", ref_prefix="ffref-",
        intro_comment=("Contenu de la page Plants and animals, genere par "
                       "tools/build_fauna_flora.py. Injecte par app.js a la premiere "
                       "ouverture."),
    )
    OUT.write_text(js, encoding="utf-8")
    print(f"{OUT.name} : {words} mots, {n} références, toutes citées")
