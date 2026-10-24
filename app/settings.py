"""Réglages persistants dans data/settings.json."""
from __future__ import annotations

import copy
import json
import os

from .paths import DATA_DIR, DIST_PATH

SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

HUBS = {
    "jita": {"id": "jita", "name": "Jita IV - Moon 4 - Caldari Navy Assembly Plant", "short": "Jita",
             "kind": "station", "station_id": 60003760, "region_id": 10000002},
    "amarr": {"id": "amarr", "name": "Amarr VIII - Emperor Family Academy", "short": "Amarr",
              "kind": "station", "station_id": 60008494, "region_id": 10000043},
    "dodixie": {"id": "dodixie", "name": "Dodixie IX - Moon 20 - Federation Navy Assembly Plant", "short": "Dodixie",
                "kind": "station", "station_id": 60011866, "region_id": 10000032},
    "rens": {"id": "rens", "name": "Rens VI - Moon 8 - Brutor Tribe Treasury", "short": "Rens",
             "kind": "station", "station_id": 60004588, "region_id": 10000030},
    "hek": {"id": "hek", "name": "Hek VIII - Moon 12 - Boundless Creation Factory", "short": "Hek",
            "kind": "station", "station_id": 60005686, "region_id": 10000042},
}

DEFAULTS = {
    "setup_done": False,
    "lang": "fr",                     # langue des noms d'objets (doit correspondre à ton client pour le Multibuy)
    "corp_name": "",
    "donate_character": "Robapin",
    "user_agent": "Cockpit/1.5 (contact: a-renseigner)",
    "esi_client_id": "",
    "esi_client_secret": "",
    "callback_url": "http://localhost:8765/callback",
    # Marchés supplémentaires (citadelles de nullsec, ex. C-N4OD). kind=structure nécessite un perso connecté
    "custom_markets": [],
    "price_market": "jita",           # marché utilisé pour valoriser achats et ventes
    "compare_market": "",             # second marché affiché dans la liste d'achats
    "buy_price_mode": "sell",         # "sell" = j'achète sur les ordres de vente (immédiat) ; "buy" = je pose des buy orders
    "sell_price_mode": "sell",        # "sell" = je pose des sell orders ; "buy" = je vends direct aux buy orders
    "sales_tax_pct": 3.6,
    "broker_fee_pct": 1.5,
    "scc_surcharge_pct": 4.0,
    "transport_isk_per_m3": 0.0,
    "skills": {
        "industry": 5, "advanced_industry": 5, "reactions": 4,
        "science_default": 4, "encryption_default": 4,
    },
    "default_bp_me": 10,
    "default_bp_te": 20,
    "bp_overrides": {},               # {bp_type_id: {"me": x, "te": y}}
    "build_policy": {
        "build_components": True,
        "build_reactions": True,
        "invent_t2": True,
        "never_build": [],            # type_ids toujours achetés
        "always_build": [],
    },
    "default_decryptor": "",
    "structures": [],
    "stock_sources": {"characters": [], "corp_divisions": [], "location_ids": []},
    "scan": {"min_margin_pct": 8, "min_daily_volume": 1, "max_unit_cost": 0, "history_top_n": 250,
             "include_t2": True, "include_reactions": True, "include_capitals": False},
    "alarm": {"detection": "auto", "watch": {"rouge": True, "orange": True, "neutre": True}, "custom_colors": {},
              "custom_tol": 30, "screen_enabled": True, "source": "window", "window_mode": "active", "window_character": "",
              "region_rel": None, "monitor": 1, "region": None, "colors": [], "tolerance": 18, "min_pixels": 25,
              "interval": 1.0, "output": "pc", "volume": 70,
              "sounds": {"rouge": "sirene", "orange": "klaxon", "neutre": "bip", "intel": "cloche"},
              "logs_enabled": False, "log_dir": "", "channels": [], "systems": [], "keywords": [], "ignore_clear": True},
    "map": {"jump_bridges": [], "jb_text": "", "home": ""},
    "arbitrage": {"hubs": ["jita", "amarr", "dodixie", "rens", "hek"], "min_profit": 1_000_000,
                  "min_margin_pct": 10, "min_avg_price": 100_000, "instant_sell": True, "history_top_n": 200},
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(path) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def distribution() -> dict:
    """Configuration fournie par celui qui distribue l'outil (ex. le directeur de corpo) :
    Client ID partagé, nom de corpo, structures communes. Fichier facultatif distribution.json."""
    return _read(DIST_PATH)


def load_settings() -> dict:
    dist = distribution()
    base = _merge(DEFAULTS, {k: v for k, v in dist.items() if k in DEFAULTS})
    s = _merge(base, _read(SETTINGS_PATH))
    # le Client ID de la distribution s'applique tant que l'utilisateur n'en a pas saisi un autre
    if not s.get("esi_client_id") and dist.get("esi_client_id"):
        s["esi_client_id"] = dist["esi_client_id"]
    if not s.get("structures") and dist.get("structures"):
        s["structures"] = dist["structures"]
    return s


def save_settings(s: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS_PATH)


def all_markets(s: dict) -> dict:
    m = dict(HUBS)
    for cm in s.get("custom_markets") or []:
        if cm.get("id"):
            m[cm["id"]] = cm
    return m
