"""Chemins : fonctionne en mode script (python run.py) comme en .exe (PyInstaller)."""
import os
import sys

FROZEN = getattr(sys, "frozen", False)
# ressources embarquées (static/) : dans le .exe elles sont décompressées dans sys._MEIPASS
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# dossier de l'application (là où se trouve le .exe ou run.py) : données utilisateur à côté
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else RES_DIR
DATA_DIR = os.path.join(APP_DIR, "data")
STATIC_DIR = os.path.join(RES_DIR, "static")
DIST_PATH = os.path.join(APP_DIR, "distribution.json")
