#!/usr/bin/env python3
"""Lance le serveur de l'observatoire : python run.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app import app  # noqa: E402

if __name__ == "__main__":
    print("Observatoire Kati Thanda - Lake Eyre : http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=False)
