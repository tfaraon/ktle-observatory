#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/aboriginal_culture.js, page « Peoples ».

La page nomme les nations dont le pays entoure le lac et couvre le
bassin, d'apres des sources publiques uniquement : determinations de
titre natif, registres des corporations titulaires, publications
gouvernementales etablies avec les Traditional Owners. Elle ne decrit
ni ceremonie, ni site sacre, ni recit.

    python tools/build_aboriginal_culture.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refbuild import build  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "frontend" / "aboriginal_culture.js"

REFS = {
    "ahchee2014": ("<i>Ah Chee v State of South Australia</i> [2014]", "<i>Ah Chee v State of South Australia</i> [2014]",
        "<i>Ah Chee v State of South Australia</i> [2014] FCA 1048. Federal Court of Australia, consent determination of native title for the Wangkangurru/Yarluyandi People.",
        "https://aiatsis.gov.au/ntpd-resource/979"),
    "aiatsismap": ("AIATSIS n.d.", "AIATSIS (n.d.)",
        "Australian Institute of Aboriginal and Torres Strait Islander Studies (n.d.) <i>Lake Eyre Basin Aboriginal Way</i> map. AIATSIS Shop.",
        "https://shop.aiatsis.gov.au/collections/all/products/map-a0-lake-eyre-basin-poster-large-flat"),
    "dewdieri": ("DEW n.d.a", "DEW (n.d.a)",
        "Department for Environment and Water, South Australia (n.d.a) The Dieri people of the Lake Eyre Basin. Interpretive panel, Killalpaninna.",
        "https://cdn.environment.sa.gov.au/landscape/docs/saal/killalpaninna_panel_prehistory6_final.pdf"),
    "dewdiamantina": ("DEW n.d.b", "DEW (n.d.b)",
        "Department for Environment and Water, South Australia (n.d.b) Many human footprints: forty thousand years walking the Country. Interpretive panel, Mungerannie.",
        "https://cdn.environment.sa.gov.au/landscape/docs/saal/8._mungerannie_aboriginal_history_final.pdf"),
    "dieri2014": ("<i>Lander v State of South Australia</i> [2014]", "<i>Lander v State of South Australia</i> [2014]",
        "<i>Lander v State of South Australia</i> [2014] FCA 125 (Dieri No. 2). Federal Court of Australia, consent determination of native title.", None),
    "dodd2012": ("<i>Dodd v State of South Australia</i> [2012]", "<i>Dodd v State of South Australia</i> [2012]",
        "<i>Dodd v State of South Australia</i> [2012] FCA 519. Federal Court of Australia, consent determination of native title for the Arabana People, 22 May 2012.",
        "https://aiatsis.gov.au/ntpd-resource/1111"),
    "eringa2008": ("<i>Eringa</i> [2008]", "<i>Eringa</i> [2008]",
        "<i>Eringa, Eringa No 2, Wangkangurru/Yarluyandi and Irrwanyere Mt Dare Native Title Claim Groups v The State of South Australia</i> [2008] FCA 1370. Federal Court of Australia.",
        "https://www.judgments.fedcourt.gov.au/judgments/Judgments/fca/single/2008/2008fca1370"),
    "gepp2017": ("<i>Gepp-Kennedy v State of South Australia</i> [2017]", "<i>Gepp-Kennedy v State of South Australia</i> [2017]",
        "<i>Gepp-Kennedy on behalf of the Dieri People v State of South Australia</i> [2017] FCA 1156. Federal Court of Australia, consent determination of native title.",
        "https://aiatsis.gov.au/ntpd-resource/1651"),
    "lander2012": ("<i>Lander v State of South Australia</i> [2012]", "<i>Lander v State of South Australia</i> [2012]",
        "<i>Lander v State of South Australia</i> [2012] FCA 427 (Dieri No. 1). Federal Court of Australia, consent determination declared at Marree Station, 1 May 2012.", None),
    "lonelyplanet2018": ("Lonely Planet 2018", "Lonely Planet (2018)",
        "Lonely Planet (2018) Aboriginal culture and heritage of Kati Thanda-Lake Eyre Basin brought alive in new map. 5 October 2018.",
        "https://www.lonelyplanet.com/articles/aboriginal-stories-kati-thanda-lake-eyre"),
    "mlt": ("Mobile Language Team n.d.", "the Mobile Language Team (n.d.)",
        "Mobile Language Team (n.d.) Dhirari. Language entry based on the Horton map of Indigenous Australia (AIATSIS, 1996), AIATSIS language code L.14.",
        "https://mobilelanguageteam.com.au/?p=163"),
    "ntpbc": ("nativetitle.org.au n.d.", "nativetitle.org.au (n.d.)",
        "nativetitle.org.au (n.d.) Prescribed bodies corporate, South Australia.",
        "https://nativetitle.org.au/region/sa?page=10"),
    "ntsa": ("South Australian Native Title Services n.d.", "South Australian Native Title Services (n.d.)",
        "South Australian Native Title Services (n.d.) Native title determinations in South Australia.",
        "https://www.nativetitlesa.org/?p=5472"),
    "qcl2018": ("Queensland Country Life 2018", "Queensland Country Life (2018)",
        "Queensland Country Life (2018) Lake Eyre Basin mapping project celebrates Aboriginal Way.",
        "https://www.queenslandcountrylife.com.au/story/5561535/lake-eyre-basin-mapping-project-celebrates-aboriginal-way/"),
    "qld2019": ("Queensland Government 2019", "the Queensland Government (2019)",
        "Queensland Government (2019) Ministerial media statement on protection of the Lake Eyre Basin, 20 December 2019.",
        "https://statements.qld.gov.au/statements/89116"),
    "qld2022": ("Queensland Government 2022", "the Queensland Government (2022)",
        "Queensland Government (2022) Traditional Owners in Lake Eyre Basin regions recognised. Ministerial media statement, 2 June 2022.",
        "https://statements.qld.gov.au/statements/95304"),
    "qldparl2023": ("Queensland Parliament 2023", "Queensland Parliament (2023)",
        "Queensland Parliament (2023) Question on Notice No. 1366, asked 26 October 2023: the Lake Eyre Basin Traditional Owner Alliance.",
        "https://documents.parliament.qld.gov.au/tableoffice/questionsanswers/2023/1366-2023.pdf"),
    "satc": ("SATC n.d.", "the South Australian Tourism Commission (n.d.)",
        "South Australian Tourism Commission (n.d.) Kati Thanda-Lake Eyre National Park.",
        "https://southaustralia.com/products/flinders-ranges-and-outback/attraction/kati-thandalake-eyre-national-park"),
}

NONE = "No determination is named in the sources cited."

TABLE = f"""<div class="table-wrap"><table class="people-table">
<thead><tr><th>Nation</th><th>Country in relation to the lake</th><th>Native title</th><th>Holding body</th></tr></thead>
<tbody>
<tr><td><b>Arabana</b><br><span class="alt">also Arabunna</span></td>
<td>West and south-west; holders of native title over the lake itself</td>
<td>About 68,823&nbsp;km&sup2; from Marree to Oodnadatta, including the lake, determined in 2012 {{c:dodd2012}}</td>
<td>Arabana Aboriginal Corporation RNTBC {{c:ntpbc}}</td></tr>
<tr><td><b>Dieri</b><br><span class="alt">also Diyari</span></td>
<td>East, along Cooper Creek from south-west of the Coongie Lakes to the lake {{c:dewdieri}}</td>
<td>Three determinations, in 2012, 2014 and 2017, the last covering about 2,115&nbsp;km&sup2; on the eastern shores of the lake {{c:lander2012,dieri2014,gepp2017}}</td>
<td>Dieri Aboriginal Corporation RNTBC {{c:ntpbc}}</td></tr>
<tr><td><b>Dhirari</b><br><span class="alt">also Thirrari, Tirari</span></td>
<td>Around the eastern side of the lake, east of Arabana, west of Dieri and north of Kuyani {{c:mlt}}</td>
<td>{NONE}</td><td></td></tr>
<tr><td><b>Wangkangurru and Yarluyandi</b></td>
<td>North, along the lower Diamantina and in the Simpson Desert {{c:dewdiamantina}}</td>
<td>About 79,600&nbsp;km&sup2; in South Australia and Queensland, determined in 2014 {{c:ahchee2014}}; Witjira National Park, jointly with the Lower Southern Arrernte, in 2008 {{c:eringa2008}}</td>
<td>Wangkangurru Yarluyandi Aboriginal Corporation RNTBC {{c:ntpbc}}</td></tr>
<tr><td><b>Kuyani</b></td>
<td>South of the lake {{c:mlt}}</td>
<td>{NONE}</td><td></td></tr>
</tbody></table></div>"""

QLD = ["Alywarra", "Boonthamurra", "Dieri", "Indjalandji-Dhidhanu", "Iningai",
       "Koa", "Kullilli", "Maiawali", "Mitakoodi", "Mithaka", "Pitta Pitta",
       "Waluwarrar", "Wangkamadla", "Wangkangurru/Yarluyandi", "Wangkumarra",
       "Yirrnendali"]

QLD_LIST = ('<ul class="nation-list">'
            + "".join(f"<li>{n}</li>" for n in QLD)
            + "</ul>")

SECTIONS = [
("About this page", "ac-about", [
"This page names the Aboriginal nations whose country lies around Kati Thanda and across the Lake Eyre Basin, drawing only on public records: native title determinations of the Federal Court, the registers of the corporations that hold native title, and material published by governments in consultation with Traditional Owners. It does not describe ceremony, sacred places or stories. That knowledge belongs to its custodians, part of it is restricted, and the decision to share it rests with them.",
"Names follow the spellings used in native title determinations and by the nations&rsquo; own organisations, and other spellings are common in the literature, among them Arabunna for Arabana, Diyari for Dieri, and Thirrari or Tirari for Dhirari. No boundaries are drawn here. Published maps of Aboriginal Australia are an approximate guide only and are not intended for land claims {c:mlt}; the boundaries recognised in law are those of the determinations themselves.",
]),
("Around the lake", "ac-lake", [
"Aboriginal people have lived in the Lake Eyre Basin for at least 40,000 years, the age that archaeological fieldwork assigns to its occupation {c:dewdieri}. The nations around the lake speak related but distinct languages, share much of their culture, and are bound to one another through kinship, trade and ceremony {c:dewdieri}.",
TABLE,
"Kati Thanda&ndash;Lake Eyre National Park is managed in partnership with the Arabana and Dieri peoples {c:satc}.",
]),
("Across the basin", "ac-basin", [
"The basin as a whole is home to 71 Aboriginal language groups {c:qld2022}. They are set out in the Lake Eyre Basin Aboriginal Way map, first proposed at an Aboriginal forum at Mount Serle in 2006 and launched in 2018 after twelve years of consultation involving several hundred people {c:qcl2018,lonelyplanet2018}. The map brings together language groups, significant places, stories, songlines and trade routes as the communities chose to share them, and its long-term care rests with the Australian Institute of Aboriginal and Torres Strait Islander Studies {c:qcl2018,aiatsismap}. It is the reference for anyone seeking the full picture, and the lists below are deliberately partial, naming only the nations that appear in the sources cited on this page.",
"In South Australia, the Yandruwandha and Yawarrawarrka, whose native title was determined in 2015 {c:ntsa}, and the Adnyamathanha are among the neighbours of the Dieri {c:dewdieri}, and the Lower Southern Arrernte hold native title with the Wangkangurru over Witjira National Park {c:eringa2008}.",
"In Queensland, sixteen nations are represented in the Queensland Lake Eyre Basin Traditional Owner Alliance {c:qldparl2023}, established with government support in 2019 to give Traditional Owners an active role in decisions on the basin {c:qld2019}:",
QLD_LIST,
"The basin also takes in part of the Northern Territory and a small part of western New South Wales {c:aiatsismap}, whose nations are recorded on the Aboriginal Way map.",
]),
]

js, words, n = build(
    REFS, SECTIONS,
    var="ABORIGINAL_CULTURE_HTML",
    eyebrow="Aboriginal culture",
    title="The peoples of Kati Thanda and its basin",
    acknowledgement=("Kati Thanda&ndash;Lake Eyre and its basin are the country of many "
                     "Aboriginal nations. We acknowledge the Arabana as Traditional Owners "
                     "of the lake, and all the Traditional Owners of the Lake Eyre Basin, "
                     "and pay our respects to their Elders past and present."),
    section_prefix="ac-", ref_prefix="acref-",
    intro_comment=("Contenu de la page Peoples de la partie Aboriginal Culture, genere "
                   "par tools/build_aboriginal_culture.py. Injecte par app.js a la "
                   "premiere ouverture."),
)
OUT.write_text(js, encoding="utf-8")
print(f"{OUT.name} : {words} mots, {n} références, toutes citées")
