#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construction commune des pages referencees du site.

Chaque citation est une cle : {c:a,b} donne une citation entre
parentheses, {n:a} une citation narrative. Une cle inconnue ou une
reference jamais citee interrompt la construction.

Un element de section commencant par « < » est insere tel quel (tableau,
liste) apres rendu des citations ; les autres deviennent des paragraphes,
soumis au controle de style : aucun tiret comme ponctuation.
"""

import html
import json
import re
import sys

CITE = re.compile(r"\{([cn]):([a-z0-9,]+)\}")


def build(refs, sections, *, var, eyebrow, title, acknowledgement,
          section_prefix, ref_prefix, intro_comment):
    used = set()

    def link(key, text_index):
        if key not in refs:
            sys.exit(f"Clé de citation inconnue : {key}")
        used.add(key)
        return (f'<a class="cite" href="#{ref_prefix}{key}">'
                f'{refs[key][text_index]}</a>')

    def render(block):
        def sub(m):
            kind, keys = m.group(1), m.group(2).split(",")
            if kind == "n":
                if len(keys) != 1:
                    sys.exit("Une citation narrative ne prend qu'une clé")
                return link(keys[0], 1)
            return "(" + "; ".join(link(k, 0) for k in keys) + ")"
        return CITE.sub(sub, block)

    body = []
    for heading, sid, items in sections:
        if not sid.startswith(section_prefix):
            sys.exit(f"Identifiant de section hors préfixe : {sid}")
        body.append(f'<section class="nh-section" id="{sid}"><h3>{heading}</h3>')
        for item in items:
            if item.lstrip().startswith("<"):
                body.append(render(item))
                continue
            plain = html.unescape(re.sub(r"<[^>]+>", "", CITE.sub("", item)))
            if "\u2014" in plain or " \u2013 " in plain or " - " in plain:
                sys.exit(f"Tiret de ponctuation dans « {heading} » : {plain[:80]}")
            body.append(f"<p>{render(item)}</p>")
        body.append("</section>")

    unused = sorted(set(refs) - used)
    if unused:
        sys.exit(f"Références jamais citées : {unused}")

    def sort_key(k):
        return re.sub(r"<[^>]+>", "", refs[k][2]).lower()

    refs_html = []
    for k in sorted(refs, key=sort_key):
        full, url = refs[k][2], refs[k][3]
        extra = (f' <a href="{url}" target="_blank" rel="noopener">'
                 f'{html.escape(url.replace("https://", ""))}</a>') if url else ""
        refs_html.append(f'<li id="{ref_prefix}{k}">{full}{extra}</li>')

    ref_sid = f"{section_prefix}references"
    toc = "".join(f'<li><a href="#{sid}">{h}</a></li>' for h, sid, _ in sections)
    toc += f'<li><a href="#{ref_sid}">References</a></li>'

    page = f"""<article class="panel nh-article">
<div class="panel-head">
<p class="eyebrow">{eyebrow}</p>
<h2>{title}</h2>
</div>
<div class="nh-layout">
<aside class="nh-toc" aria-label="Contents">
<p class="nh-toc-title">Contents</p>
<ol>{toc}</ol>
</aside>
<div class="nh-body prose-body">
<p class="nh-acknowledgement">{acknowledgement}</p>
{''.join(body)}
<section class="nh-section" id="{ref_sid}"><h3>References</h3>
<ol class="nh-references">{''.join(refs_html)}</ol>
</section>
</div>
</div>
</article>"""

    words = len(re.sub(r"<[^>]+>", " ", "".join(body)).split())
    js = (f"/* {intro_comment} */\n"
          f"const {var} = {json.dumps(page, ensure_ascii=False)};\n")
    return js, words, len(refs)


def shared_refs(keys, source="build_natural_history.py"):
    """References d'une autre page, lues a la source plutot que recopiees.

    Une reference verifiee n'existe ainsi qu'a un seul endroit. On
    n'execute que le litteral REFS du script source, sans lancer sa
    construction.
    """
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent / source).read_text(encoding="utf-8")
    start = src.index("REFS = {")
    end = src.index("\n}\n", start) + 2
    refs = ast.literal_eval(src[start + len("REFS = "):end])
    missing = [k for k in keys if k not in refs]
    if missing:
        sys.exit(f"Références absentes de {source} : {missing}")
    return {k: refs[k] for k in keys}
