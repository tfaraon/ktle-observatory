#!/usr/bin/env python3
"""Point d'entree WSGI pour un serveur de production (gunicorn).

    gunicorn -c deploy/gunicorn.conf.py deploy.wsgi:app

Le serveur integre de Flask (`python run.py`) convient au poste de
travail mais pas a une mise en ligne : mono-thread, sans limite de
requetes, sans journalisation exploitable.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402,F401
