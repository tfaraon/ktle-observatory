#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de l'export des niveaux au format de la toolbox SWIR
(pipeline/export_levels.py).

La toolbox lit le CSV avec pd.read_csv, sans ignorer les lignes #, et
attend deux colonnes date et water_level_m, un niveau par date. Le
telechargement du site, concu comme une archive documentee, ne
remplissait aucune de ces conditions.

Execution :  python tests/test_export_levels.py
"""

import csv
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import export_levels as ex  # noqa: E402

series = [
    {"date": "2026-08-14T03:10:00", "wse": -13.04},
    {"date": "2026-08-14T21:40:00", "wse": -13.02},     # même jour
    {"date": "2026-08-15T03:10:00", "wse": -12.85},
    {"date": "2026-08-16T03:10:00", "wse": None},        # à ignorer
]

rows = ex.daily_levels(series)
assert [d for d, _, _ in rows] == ["2026-08-14", "2026-08-15"]
assert abs(rows[0][1] - (-13.03)) < 1e-9, "passes d'une journée moyennées"
assert rows[0][2] == 2 and rows[1][2] == 1

with tempfile.TemporaryDirectory() as td:
    out = ex.write(rows, Path(td) / "sub" / "levels.csv")
    text = out.read_text(encoding="utf-8")

    # Aucune ligne de commentaire : pd.read_csv les lirait comme données
    assert "#" not in text, "le fichier ne doit contenir aucun commentaire"
    with open(out, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == ["date", "water_level_m"], header

    # Lecture par pandas avec les réglages par défaut, comme la toolbox
    table = pd.read_csv(out)
    assert list(table.columns) == ["date", "water_level_m"]
    assert len(table) == 2
    assert table["date"].is_unique, "un seul niveau par date"
    assert pd.to_datetime(table["date"], errors="coerce").notna().all()

    # Décalage de datum appliqué sur demande
    shifted = ex.write(rows, Path(td) / "ahd.csv", offset=0.5)
    t2 = pd.read_csv(shifted)
    assert abs(t2["water_level_m"].iloc[0] - (-12.53)) < 1e-6

assert ex.daily_levels([]) == []

print("OK — export sans commentaire, un niveau par date, colonnes attendues "
      "par la toolbox, décalage appliqué sur demande.")
