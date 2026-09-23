#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frise des remplissages du lac -> frontend/floods.js

Seuls les remplissages que le site sait citer figurent ici. 2000 et 2019
en sont absents faute de source verifiee : les ajouter demande d'abord
une reference.

    python tools/build_floods.py
"""

import refbuild

REFS = dict(refbuild.shared_refs([
    "badman1991a", "arnold1991", "leycboat", "kotwicki1986", "kotwicki1991",
    "ummenhofer2015", "bye1978", "bonython1989", "devogel2004", "poulter2014",
    "fasullo2013", "rai2026b", "habeck2014",
]))
REFS["faraon2026"] = (
    "Faraon et al. in preparation", "Faraon et al. (in preparation)",
    "Faraon, T. et al. (in preparation) Using satellite imagery of the Lake Eyre basin to "
    "understand hydrodynamics during the 2025 flood event.", None)

STRIP = (
    '<nav class="fl-strip" aria-label="Fillings of the lake">'
    '<a class="fl-year fl-full" href="#fl-1950"><b>1950</b><span>Complete filling</span></a>'
    '<a class="fl-year fl-full" href="#fl-1974"><b>1974</b><span>Greatest on record</span></a>'
    '<a class="fl-year fl-small" href="#fl-1984"><b>1984</b><span>Minor filling</span></a>'
    '<a class="fl-year fl-small" href="#fl-1989"><b>1989</b><span>Minor filling</span></a>'
    '<a class="fl-year fl-wet" href="#fl-2010"><b>2010&ndash;2011</b><span>Wet years</span></a>'
    '<a class="fl-year fl-full" href="#fl-2025"><b>2025</b><span>Record on the Cooper</span></a>'
    "</nav>")

SECTIONS = [
("A century of fillings", "fl-century", [
"Water reaches Kati Thanda often enough to be expected and rarely enough to be an event. Cooper Creek "
"floods crossed the Birdsville Track ten times between 1866 and 1917, not once from 1918 to 1949 and nine "
"times from 1951 to 1991, yet they reached the lake only eleven times between 1890 and 1991 {c:badman1991a}. "
"The rhythm follows the tropical Pacific, large fillings coinciding with strong La Ni&ntilde;a years "
"{c:kotwicki1991}, and {n:kotwicki1986} counted 1891, 1906, 1941, 1949&ndash;1951, 1953, 1955&ndash;1959 and "
"1963 among the significant filling years. The fillings below are those this site can document from published "
"sources; others, such as 2000 and 2019, are missing here for want of a reference rather than for want of water.",
"{fig:dry-lake|The lake between fillings: a white plain of salt, the state in which it spends most of any decade.}",
STRIP,
]),
("1950", "fl-1950", [
"The 1950 flood was one of only two complete fillings of the twentieth century, and the one time Cooper Creek "
"provided most of the water {c:badman1991a}. It closed a dry half century during which the Cooper had not once "
"crossed the Birdsville Track, and opened a run of wet years that continued through 1951, 1953 and the late "
"1950s {c:kotwicki1986}.",
]),
("1974", "fl-1974", [
"Australia&rsquo;s wettest year on record {c:ummenhofer2015} produced the greatest filling of the historical "
"period: about 6&nbsp;m of water and some 30&nbsp;km&sup3; {c:bye1978,kotwicki1986,bonython1989,devogel2004}. "
"At that level Lake Eyre North measured 144&nbsp;km by 77&nbsp;km and covered 8,430&nbsp;km&sup2;, Lake Eyre "
"South 64&nbsp;km by 24&nbsp;km and 1,260&nbsp;km&sup2;, and of the water that entered between 1974 and 1976 "
"some 38&nbsp;km&sup3; came down the Warburton, 2&nbsp;km&sup3; down the Cooper and 8&nbsp;km&sup3; from the "
"local rivers {c:badman1991a}. The Goyder Channel carried water from the northern lake to the southern, and "
"boats reached the lake in numbers for the first time {c:leycboat}. Shorelines at or near that level show that "
"such fillings belong to the lake&rsquo;s ordinary behaviour rather than to accident {c:habeck2014}.",
"{n:kotwicki1986} set out the full balance of that filling. Between January 1974 and June 1976 the lake took in "
"38&nbsp;km&sup3; from the Diamantina system, 2&nbsp;km&sup3; from the Cooper, 8&nbsp;km&sup3; from the local "
"rivers and another 8&nbsp;km&sup3; as rain falling directly on its surface, 56&nbsp;km&sup3; in all, against "
"39.5&nbsp;km&sup3; lost to evaporation, leaving 16.5&nbsp;km&sup3; in June 1976. The Goyder Channel began to "
"flow on 19 March 1974 and ran until October, when the two lakes settled at the same level of "
"&minus;9.5&nbsp;m. The salt crust went the same way as the water: dissolved in Jackboot Bay by September "
"1974, in Belt Bay by August 1975, and in the thickest part of Madigan Gulf by the end of that year, so that "
"by early 1976 no crust remained and the brine of Madigan Gulf had concentrated to 57&nbsp;g of salt a "
"kilogram {c:kotwicki1986}.",
]),
("1984", "fl-1984", [
"January 1984 was extraordinary in a way that has nothing to do with its size. {n:kotwicki1986}, who devoted a "
"chapter of his study to it, judged it so for two reasons: for the first time on record Lake Eyre South filled "
"independently and overflowed into Lake Eyre North, an event that had been regarded as obviously impossible, "
"and both lakes filled in a matter of days from rain that fell on or near them rather than from any river. The "
"rain came from a tropical depression that formed in the north-west of the continent on 9 and 10 January and "
"tracked slowly south-east across northern South Australia; the Frome, ten kilometres south of Marree, cut the "
"road and the old railway line {c:kotwicki1986}. The Lake Eyre Yacht Club records the same sequence, the "
"channel running from south to north for the first time Europeans had seen, and Lake Eyre North filling to "
"3.5&nbsp;m {c:leycboat}. {n:badman1991a} gave a different account, attributing the filling to the western "
"rivers alone after up to 375&nbsp;mm of rain fell over their catchments in about a week; the two records made "
"at the time of the event agree against him.",
]),
("1989", "fl-1989", [
"Local rain again filled Lake Eyre South, which overflowed north and brought Lake Eyre North to 3.0&nbsp;m "
"{c:leycboat}. Modest as it was, this filling drew visitors to the shores in unprecedented numbers, four years "
"after the national park was proclaimed {c:arnold1991}.",
]),
("2010 and 2011", "fl-2010", [
"The wet years of 2010 and 2011 were felt far beyond the basin. The greening of Australia&rsquo;s semi-arid "
"interior in 2011 made a measurable contribution to the global land carbon sink {c:poulter2014}, and the water "
"held inland that year briefly lowered global mean sea level {c:fasullo2013}. They are a reminder that what "
"fills this lake is a continental event, not a local one.",
"{fig:flood-2011-lake|The lake holding water in May 2011, at the end of two wet years.}",
]),
("2025", "fl-2025", [
"The 2025 flood produced the highest discharge ever recorded on Cooper Creek, surpassing 1974 with a peak of "
"814&nbsp;GL a day and a floodplain up to 55&nbsp;km wide {c:rai2026b}. The first wave reached the lake on 29 "
"April, down the Warburton, and a second arrived through Cooper Creek at the end of June; the lake then dried "
"through the second half of the year {c:faraon2026}. Large though it was, the event sits within the basin&rsquo;s "
"ordinary range rather than beyond it, which is what makes it worth following closely: its sequence is set out "
"under <a href=\"#rain-to-lake\">From rain to lake</a>.",
"{fig:flood-2025-lake|The first flood wave spreading across the northern lake bed in May 2025, down the Warburton and Kalaweerina Grooves.}",
]),
]

if __name__ == "__main__":
    js, words, refs = refbuild.build(
        REFS, SECTIONS, var="FLOODS_HTML", eyebrow="The lake",
        title="Fillings of Kati Thanda",
        acknowledgement=("Kati Thanda&ndash;Lake Eyre lies on Arabana country. We acknowledge "
                         "the Arabana people as its Traditional Owners."),
        section_prefix="fl-", ref_prefix="flref-",
        intro_comment="Frise des remplissages, construite par tools/build_floods.py")
    open("frontend/floods.js", "w", encoding="utf-8").write(js)
    print(f"floods.js : {words} mots, {refs} références, toutes citées")
