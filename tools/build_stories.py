#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit frontend/stories.js, sous-onglet Stories de Aboriginal culture.

Regle de la page : ne figurent que les recits que les detenteurs du
savoir, ou les organisations qui parlent pour eux, ont eux-memes rendus
publics. On renvoie vers leur recit sans le raconter a leur place : la
propriete culturelle et intellectuelle reste la leur (ICIP), et une
reformulation, meme fidele, deciderait pour eux de la forme du recit.

Les recueils etablis par des missionnaires ou des anthropologues ne sont
pas listes, quelle que soit leur anciennete ou leur disponibilite.

    python tools/build_stories.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refbuild import build  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "frontend" / "stories.js"

REFS = {
    "abc2012": ("ABC News 2012", "ABC News (2012)",
        "ABC News (2012) New name adopted for outback Lake Eyre. 20 December 2012.",
        "https://www.abc.net.au/news/2012-12-20/new-name-adopted-for-outback-lake-eyre/4436212"),
    "abc2025": ("ABC News 2025", "ABC News (2025)",
        "ABC News (2025) Visitors still walking on Kati Thanda-Lake Eyre months after foot traffic ban. 22 June 2025.",
        "https://www.abc.net.au/news/2025-06-22/kati-thanda-lake-eyre-first-fill-since-recreational-access-ban/105371816"),
    "aiatsismap": ("AIATSIS n.d.", "AIATSIS (n.d.)",
        "Australian Institute of Aboriginal and Torres Strait Islander Studies (n.d.) <i>Lake Eyre Basin Aboriginal Way</i> map. AIATSIS Shop.",
        "https://shop.aiatsis.gov.au/collections/all/products/map-a0-lake-eyre-basin-poster-large-flat"),
    "deeptime": ("ABC Deep Time n.d.a", "ABC Deep Time (n.d.a)",
        "ABC News Story Lab (n.d.a) About the project. <i>Deep Time Australia</i>, including its Indigenous Cultural and Intellectual Property protocol.",
        "https://www.abc.net.au/news/deeptime/about/"),
    "dtcreation": ("ABC Deep Time n.d.b", "ABC Deep Time (n.d.b)",
        "Syd Strangeways and Arabana Aboriginal Corporation (n.d.b) Kati Thanda creation. <i>Deep Time Australia</i>, ABC News.",
        "https://www.abc.net.au/news/deeptime/about/arabana-aboriginal-corporation/kati-thanda-lake-eyre-creation/"),
    "lonelyplanet2018": ("Lonely Planet 2018", "Lonely Planet (2018)",
        "Lonely Planet (2018) Aboriginal culture and heritage of Kati Thanda-Lake Eyre Basin brought alive in new map. 5 October 2018.",
        "https://www.lonelyplanet.com/articles/aboriginal-stories-kati-thanda-lake-eyre"),
    "slsaarabana": ("SLSA 2026a", "the State Library of South Australia (2026a)",
        "State Library of South Australia (2026a) Aboriginal people of South Australia: Arabana. Research guide.",
        "https://guides.slsa.sa.gov.au/Aboriginal_peopleSA/Arabana"),
    "slsadieri": ("SLSA 2026b", "the State Library of South Australia (2026b)",
        "State Library of South Australia (2026b) Aboriginal people of South Australia: Dieri. Research guide.",
        "https://guides.slsa.sa.gov.au/Aboriginal_peopleSA/Dieri"),
    "stuart1991": ("Stuart 1991", "Stuart (1991)",
        "Stuart, R. (1991) An Aboriginal viewpoint. In: Badman, F.J., Arnold, B.K. and Bell, S.L. (eds) <i>A Natural History of the Lake Eyre Region: A Visitor&rsquo;s Guide</i>, p. 61. National Parks and Wildlife Service, Northern Consultative Committee, Port Augusta.",
        None),
}

DT = "https://www.abc.net.au/news/deeptime/about/"


def entry(title, meta, url=None, book=False):
    t = f"<i>{title}</i>" if book else title
    head = (f'<a class="story-title" href="{url}" target="_blank" rel="noopener">{t}</a>'
            if url else f'<span class="story-title">{t}</span>')
    return f'<li>{head}<span class="story-meta">{meta}</span></li>'


ARABANA_ONLINE = '<ul class="story-list">' + "".join([
    entry("Kati Thanda creation",
          "Syd Strangeways and the Arabana Aboriginal Corporation, in the ABC&rsquo;s Deep Time project",
          DT + "arabana-aboriginal-corporation/kati-thanda-lake-eyre-creation/"),
    entry("Kati Thanda sacred water",
          "Arabana Aboriginal Corporation, in the ABC&rsquo;s Deep Time project",
          DT + "arabana-aboriginal-corporation/kati-thanda-sacred-water"),
    entry("Seven Sisters, Arabana",
          "Syd Strangeways and the Arabana Aboriginal Corporation, in the ABC&rsquo;s Deep Time project",
          DT + "arabana-aboriginal-corporation/arabana-seven-sisters"),
    entry("New name adopted for outback Lake Eyre",
          "Aaron Stuart, chair of the Arabana Aboriginal Corporation, speaking to ABC News in 2012",
          REFS["abc2012"][3]),
]) + "</ul>"

ARABANA_BOOKS = '<ul class="story-list">' + "".join([
    entry("Yarnin&rsquo; with grandpa: stories from my life on Arabana Country",
          "Thanthi Syd Strangeways, 2021",
          "https://www.catalog.slsa.sa.gov.au/record=b3539963~S1", book=True),
    entry("Talking Sideways: stories and conversations from Finniss Springs",
          "Reg Dodd and Malcolm McKinnon, University of Queensland Press, 2019; an extract appeared in "
          '<a href="https://insidestory.org.au/we-talk-kind-of-sideways-because-thats-the-respectful-way/" '
          'target="_blank" rel="noopener">Inside Story</a> in 2020',
          "https://www.uqp.com.au/books/talking-sideways-stories-and-conversations-from-finniss-springs",
          book=True),
    entry("Wathili family, Wibma stories, Wadlhu country",
          "Arabana Elders and Veronica Arbon, 2010",
          "http://www.catalog.slsa.sa.gov.au:80/record=b2556908~S1", book=True),
    entry("Ari Finniss-inga minhathirnda: what we do at Finnis",
          "Arabana Wangka Community Workshop, 2019",
          "https://www.catalog.slsa.sa.gov.au/record=b3539969~S1", book=True),
    entry("Lake Eyre is calling: Ankaku for life",
          "Kevin Buzzacott, 2002",
          "http://www.catalog.slsa.sa.gov.au/record=b1581066", book=True),
    entry("Learning times: an experience of Arabana life and mission education",
          "Reg Dodd and Jen Gibson, <i>Aboriginal History</i> 13, 80&ndash;93, 1989"),
]) + "</ul>"

SECTIONS = [
("How this page works", "st-about", [
"This page lists only stories and accounts that Aboriginal knowledge holders, or the organisations that speak for them, have chosen to make public, and it links to them rather than retelling them. The stories remain the cultural and intellectual property of their custodians. The ABC&rsquo;s Deep Time project, which publishes several of them, includes each story only with the free, prior and informed consent of its knowledge holders, and does not allow it to be reproduced without their permission {c:deeptime}.",
"Aboriginal and Torres Strait Islander readers are advised that the linked sources may contain the names and images of people who have died. Records of stories made by missionaries, anthropologists and other outsiders are not listed here, however old or easy to find, because the decision to publish them was not made by the peoples whose stories they are.",
]),
("Arabana", "st-arabana", [
"Kati Thanda lies on Arabana country. The Arabana Aboriginal Corporation and Arabana knowledge holder Syd Strangeways have shared three stories through the ABC&rsquo;s Deep Time project {c:deeptime}. The Arabana describe the full story of the lake&rsquo;s creation as sensitive and sacred, used in the initiation of young men, with songs that are secret; the version online is the one they chose to share {c:dtcreation}. When the lake&rsquo;s dual name was adopted in 2012, Aaron Stuart, then chair of the Arabana Aboriginal Corporation, spoke publicly about the name and its place in Arabana Dreaming {c:abc2012}.",
ARABANA_ONLINE,
"Arabana elders have also written their own books, listed by the State Library of South Australia {c:slsaarabana}.",
ARABANA_BOOKS,
"Arabana people say that their ancestors and spiritual beings live on the lake. Arabana Aboriginal Corporation director Colleen Raven Strangways has explained that a footprint on its surface stays there until the next big flood, which is why the Arabana ask visitors to enjoy the lake without walking or boating on it {c:abc2025}.",
]),
("Across the basin", "st-basin", [
"For the basin as a whole, the Lake Eyre Basin Aboriginal Way map gathers stories, songlines, trade routes and significant places as the communities of its 71 language groups chose to share them, after twelve years of consultation {c:lonelyplanet2018,aiatsismap}. It is the place to begin for the stories of other nations.",
"The natural history of the Lake Eyre region that the National Parks and Wildlife Service published in 1991 includes a chapter by Rex Stuart, then the Service&rsquo;s Aboriginal liaison officer and adviser to the committee that produced the book, drawn from his own experience of the area and its needs {c:stuart1991}. The book is in print only, and the chapter is not summarised here.",
"We have not found Dieri stories published by Dieri knowledge holders themselves. The State Library of South Australia lists Dieri narratives recorded by missionaries and anthropologists from the nineteenth century onward {c:slsadieri}; following the rule of this page, they are not listed here.",
"Custodians who would like a story added, corrected or removed can reach the maintainers of this site through its <a href=\"https://github.com/tfaraon/ktle-observatory/issues\" target=\"_blank\" rel=\"noopener\">public repository</a>.",
]),
]

js, words, n = build(
    REFS, SECTIONS,
    var="STORIES_HTML",
    eyebrow="Aboriginal culture",
    title="Stories shared by their custodians",
    acknowledgement=("These stories belong to their custodians. We thank the knowledge "
                     "holders who have chosen to share them, and pay our respects to "
                     "Elders past and present."),
    section_prefix="st-", ref_prefix="stref-",
    intro_comment=("Contenu du sous-onglet Stories, genere par tools/build_stories.py. "
                   "Liens vers les recits publies par leurs detenteurs, jamais de "
                   "reformulation."),
)
OUT.write_text(js, encoding="utf-8")
print(f"{OUT.name} : {words} mots, {n} références, toutes citées")
