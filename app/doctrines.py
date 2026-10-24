"""Stockage des doctrines.

- Doctrines personnelles : data/doctrines.json (modifiables).
- Doctrines officielles de la corpo (lecture seule) : clé "doctrines" de distribution.json
  et/ou fichier JSON publié à l'adresse "doctrines_url" (mis en cache dans data/corp_doctrines.json).
Format d'échange (export/import) : {"format": "eve-indy-doctrines", "version": 1, "doctrines": [...]}
"""
from __future__ import annotations

import json
import os
import time
import uuid

from .paths import DATA_DIR
from .settings import distribution

USER_PATH = os.path.join(DATA_DIR, "doctrines.json")
CORP_CACHE = os.path.join(DATA_DIR, "corp_doctrines.json")
ROLES = ["DPS", "Logistique", "Tackle", "Ewar", "Boosts", "Éclaireur", "FC", "Bombardier", "Capital", "Autre"]


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _write(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _normalize(docs, official):
    out = []
    for d in docs or []:
        if not isinstance(d, dict) or not d.get("name"):
            continue
        d = dict(d)
        d.setdefault("id", uuid.uuid4().hex[:10])
        if official and not str(d["id"]).startswith("corp-"):
            d["id"] = "corp-" + str(d["id"])
        d["official"] = official
        d.setdefault("description", "")
        fits = []
        for f in d.get("fits") or []:
            if f.get("ship_type_id") and isinstance(f.get("items"), list):
                f = dict(f)
                f.setdefault("id", uuid.uuid4().hex[:10])
                f.setdefault("role", "DPS")
                f.setdefault("notes", "")
                fits.append(f)
        d["fits"] = fits
        out.append(d)
    return out


def load_user():
    return _normalize((_read(USER_PATH) or {}).get("doctrines"), False)


def save_user(docs):
    for d in docs:
        d["official"] = False
    _write(USER_PATH, {"format": "eve-indy-doctrines", "version": 1, "doctrines": docs})


def load_corp():
    docs = list(distribution().get("doctrines") or [])
    cached = _read(CORP_CACHE) or {}
    docs += cached.get("doctrines") or []
    return _normalize(docs, True)


def save_corp_cache(payload):
    payload = payload if isinstance(payload, dict) else {"doctrines": payload}
    _write(CORP_CACHE, {"doctrines": payload.get("doctrines") or [], "fetched": time.time()})


def corp_cache_time():
    return (_read(CORP_CACHE) or {}).get("fetched")


def all_doctrines():
    return load_corp() + load_user()


def export_payload(docs):
    clean = []
    for d in docs:
        clean.append({"id": str(d["id"]).replace("corp-", ""), "name": d["name"], "description": d.get("description", ""),
                      "fits": [{k: f[k] for k in ("id", "name", "ship_type_id", "items", "role", "notes") if k in f}
                               for f in d["fits"]]})
    return {"format": "eve-indy-doctrines", "version": 1, "exported": time.strftime("%Y-%m-%d"), "doctrines": clean}
