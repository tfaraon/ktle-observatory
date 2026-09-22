#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de la recuperation iNaturalist (pipeline/fetch_inaturalist.py), sans
reseau : les reponses de l'API sont simulees.

Ce qui est verifie engage le site vis-a-vis des observateurs et
d'iNaturalist : seules les photos sous licence sont reprises, avec leur
attribution ; une localisation masquee ne devient jamais un point sur la
carte ; le nom reel de l'observateur n'est pas conserve ; les requetes
sont espacees ; une panne garde le dernier jeu valide.

Execution :  python tests/test_inaturalist.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import fetch_inaturalist as fi  # noqa: E402

OBS = {"total_results": 57, "results": [
    {"id": 1, "uri": "https://www.inaturalist.org/observations/1", "observed_on": "2026-09-18",
     "quality_grade": "research", "species_guess": "Banded Stilt",
     "taxon": {"name": "Cladorhynchus leucocephalus", "preferred_common_name": "Banded Stilt",
               "rank": "species", "iconic_taxon_name": "Aves"},
     "user": {"login": "saltflat", "name": "Real Person"},
     "geojson": {"type": "Point", "coordinates": [137.0512345, -28.8912345]},
     "photos": [{"url": "https://static.inaturalist.org/photos/1/square.jpg",
                 "license_code": "cc-by-nc", "attribution": "(c) saltflat, some rights reserved (CC BY-NC)"}]},
    {"id": 2, "observed_on": "2026-09-17", "quality_grade": "needs_id",
     "taxon": {"name": "Ctenophorus maculosus", "iconic_taxon_name": "Reptilia"},
     "user": {"login": "dragonwatch", "name": "Another Person"}, "obscured": True,
     "geojson": {"type": "Point", "coordinates": [137.2, -28.7]},
     "photos": [{"url": "https://static.inaturalist.org/photos/2/square.jpg",
                 "license_code": None, "attribution": "(c) dragonwatch, all rights reserved"}]},
    {"id": 3, "observed_on": "2026-09-16", "quality_grade": "casual", "geoprivacy": "private",
     "taxon": {"name": "Tecticornia"}, "user": {"login": "x"},
     "geojson": {"type": "Point", "coordinates": [137.3, -29.1]}, "photos": []},
]}
SPP = {"total_results": 21, "results": [
    {"count": 9, "taxon": {"id": 4217, "name": "Pelecanus conspicillatus",
                           "preferred_common_name": "Australian Pelican", "iconic_taxon_name": "Aves",
                           "default_photo": {"url": "https://static.inaturalist.org/photos/9/square.jpg",
                                             "license_code": "cc-by", "attribution": "(c) someone"}}}]}
PPL = {"total_results": 11, "results": []}


def fake(responses, calls):
    def f(path, params):
        calls.append((path, dict(params)))
        r = responses[path]
        if isinstance(r, Exception):
            raise r
        return r
    return f


pauses = []
with tempfile.TemporaryDirectory() as td:
    fi.OUT_FILE = Path(td) / "inaturalist.json"

    # ── Filtre : emprise du lac tant qu'aucun projet n'existe ──
    calls = []
    d = fi.update({}, fetch=fake({"/observations": OBS, "/observations/species_counts": SPP,
                                  "/observations/observers": PPL}, calls),
                  sleep=pauses.append)
    assert [c[0] for c in calls] == ["/observations", "/observations/species_counts",
                                     "/observations/observers"]
    assert all("swlat" in c[1] and "project_id" not in c[1] for c in calls)
    assert all(c[1]["verifiable"] == "true" for c in calls)
    assert calls[1][1]["per_page"] == 300, "toutes les espèces, pour les groupes"
    assert len(pauses) == 2 and all(p >= 1.0 for p in pauses), "requêtes espacées"
    assert d["source"] == "area" and d["links"]["project"] is None
    assert "swlat=-29.8" in d["links"]["explore"]
    assert d["totals"] == {"observations": 57, "species": 21, "observers": 11}

    # ── Licences : photo sous licence gardée, « tous droits réservés » écartée ──
    o1, o2, o3 = d["recent"]
    assert o1["photo"]["license"] == "CC-BY-NC"
    assert o1["photo"]["medium"].endswith("/medium.jpg")
    assert "saltflat" in o1["photo"]["attribution"]
    assert o2["photo"] is None
    assert d["species"][0]["photo"]["license"] == "CC-BY"

    # ── Localisations : précises arrondies, masquées ou privées retirées ──
    assert o1["coords"] == [-28.8912, 137.0512]
    assert o2["obscured"] and o2["coords"] is None
    assert o3["obscured"] and o3["coords"] is None

    # ── Observateur : identifiant public seulement ──
    text = fi.OUT_FILE.read_text(encoding="utf-8")
    assert o1["observer"] == "saltflat"
    assert "Real Person" not in text and "Another Person" not in text

    # ── Projet configuré : il remplace l'emprise partout ──
    calls = []
    d2 = fi.update({"inaturalist": {"project": "kati-thanda-lake-eyre"}},
                   fetch=fake({"/observations": OBS, "/observations/species_counts": SPP,
                               "/observations/observers": PPL}, calls),
                   sleep=lambda s: None, write=False)
    assert all(c[1]["project_id"] == "kati-thanda-lake-eyre" and "swlat" not in c[1] for c in calls)
    assert d2["links"]["project"].endswith("/projects/kati-thanda-lake-eyre")
    assert "project_id=kati-thanda-lake-eyre" in d2["filter"]

    # ── Panne : dernier jeu valide conservé et marqué ──
    d3 = fi.update({}, fetch=fake({"/observations": OSError("réseau coupé")}, []),
                   sleep=lambda s: None)
    assert d3["stale"] and d3["totals"]["observations"] == 57 and d3["errors"]

    # ── Démonstration : jamais confondue avec un jeu réel ──
    demo = fi.update({}, demo=True, sleep=lambda s: None)
    assert demo["demo"] is True
    fi.OUT_FILE.unlink()
    try:
        fi.update({}, fetch=fake({"/observations": OSError("coupé")}, []), sleep=lambda s: None)
        raise AssertionError("aurait dû échouer sans fichier précédent")
    except SystemExit:
        pass

# ── Bornes de configuration ──
s = fi.settings({"inaturalist": {"recent": 500, "top_species": 0, "max_species": 9000}})
assert s["recent"] == 60 and s["top_species"] == 1 and s["max_species"] == 500

print("OK — photos sous licence seules, attribution gardée, localisations masquées "
      "retirées, identifiant public seulement, requêtes espacées, projet ou emprise, "
      "panne et démonstration.")
