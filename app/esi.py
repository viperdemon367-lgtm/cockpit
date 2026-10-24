"""Accès aux données dynamiques : ESI (API officielle CCP), Fuzzwork (agrégats de marché) et SSO EVE.

- Prix ajustés + indices de coût système : ESI public
- Prix de marché d'une station NPC (Jita, Amarr…) : market.fuzzwork.co.uk, repli sur ESI si indisponible
- Marché d'une citadelle (ex. C-N4OD) : ESI authentifié (scope esi-markets.structure_markets.v1)
- Historique (volume/jour) : ESI public
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse

import httpx

from .paths import DATA_DIR

ESI = "https://esi.evetech.net"
COMPAT_DATE = "2026-06-01"   # X-Compatibility-Date : à relever si CCP fait évoluer une route utilisée
FUZZ = "https://market.fuzzwork.co.uk/aggregates/"
SSO_AUTH = "https://login.eveonline.com/v2/oauth/authorize"
SSO_TOKEN = "https://login.eveonline.com/v2/oauth/token"

SCOPES = [
    "esi-assets.read_assets.v1",
    "esi-assets.read_corporation_assets.v1",
    "esi-corporations.read_divisions.v1",
    "esi-characters.read_blueprints.v1",
    "esi-skills.read_skills.v1",
    "esi-universe.read_structures.v1",
    "esi-markets.structure_markets.v1",
    "esi-industry.read_character_jobs.v1",
    "esi-skills.read_skillqueue.v1",
    "esi-fittings.read_fittings.v1",
    "esi-fittings.write_fittings.v1",
    "esi-characters.read_contacts.v1",
    "esi-corporations.read_contacts.v1",
    "esi-alliances.read_contacts.v1",
    "esi-location.read_location.v1",
    "esi-location.read_ship_type.v1",
    "esi-ui.write_waypoint.v1",
    "esi-search.search_structures.v1",
    "esi-ui.open_window.v1",
]

TOKENS_PATH = os.path.join(DATA_DIR, "tokens.json")
CACHE_PATH = os.path.join(DATA_DIR, "http_cache.json")


class TTLCache:
    """Petit cache clé/valeur persistant sur disque."""

    def __init__(self, path=CACHE_PATH):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except Exception:
                self.data = {}
        self._dirty = False

    def get(self, key, ttl):
        e = self.data.get(key)
        if e and time.time() - e["t"] < ttl:
            return e["v"]
        return None

    def set(self, key, value):
        self.data[key] = {"t": time.time(), "v": value}
        self._dirty = True

    def flush(self):
        if not self._dirty:
            return
        # purge des entrées vieilles de plus de 3 jours
        now = time.time()
        self.data = {k: v for k, v in self.data.items() if now - v["t"] < 3 * 86400}
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh)
        os.replace(tmp, self.path)
        self._dirty = False


class EsiError(RuntimeError):
    pass


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def parse_sov(rows) -> dict:
    """Normalise les différents formats de souveraineté ESI -> {"système": {alliance_id, faction_id}}."""
    out = {}
    for x in rows or []:
        if not isinstance(x, dict):
            continue
        sid = _first(x, "system_id", "solar_system_id", "systemId", "solarSystemId")
        owner = x.get("owner") if isinstance(x.get("owner"), dict) else {}
        ally = _first(x, "alliance_id", "allianceId") or _first(owner, "alliance_id", "allianceId")
        fac = _first(x, "faction_id", "factionId") or _first(owner, "faction_id", "factionId")
        if owner and not (ally or fac):      # format « owner: {id, type} »
            oid, otype = _first(owner, "id", "owner_id"), str(_first(owner, "type", "owner_type") or "").lower()
            if oid and "faction" in otype:
                fac = oid
            elif oid:
                ally = oid
        if sid and (ally or fac):
            out[str(int(sid))] = {"alliance_id": ally, "faction_id": fac}
    return out


class EsiClient:
    def __init__(self, settings_getter):
        self.settings_getter = settings_getter
        self.cache = TTLCache()
        self.client = httpx.AsyncClient(timeout=60, follow_redirects=True)
        self.sem = asyncio.Semaphore(12)
        self.tokens = self._load_tokens()
        self._pkce: dict[str, str] = {}

    # ------------------------------------------------------------------ http
    def _headers(self, token: str | None = None):
        s = self.settings_getter()
        h = {"User-Agent": s.get("user_agent") or "Cockpit",
             "X-Compatibility-Date": COMPAT_DATE, "Accept": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def _get(self, url, params=None, token=None, retries=3):
        last = None
        for attempt in range(retries):
            async with self.sem:
                try:
                    r = await self.client.get(url, params=params, headers=self._headers(token))
                except httpx.HTTPError as e:
                    last = e
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            remain = r.headers.get("X-ESI-Error-Limit-Remain")
            if remain is not None and int(remain) < 15:
                await asyncio.sleep(int(r.headers.get("X-ESI-Error-Limit-Reset", "10")))
            if r.status_code == 200:
                return r
            if r.status_code in (420, 429, 502, 503, 504):
                await asyncio.sleep(2 * (attempt + 1))
                last = EsiError(f"{r.status_code} sur {url}")
                continue
            if r.status_code == 404:
                return r
            raise EsiError(f"ESI {r.status_code} sur {url} : {r.text[:200]}")
        raise EsiError(f"Échec après {retries} essais : {url} ({last})")

    async def _get_paged(self, url, params=None, token=None):
        params = dict(params or {})
        r = await self._get(url, {**params, "page": 1}, token)
        out = list(r.json() or [])
        pages = int(r.headers.get("X-Pages", "1"))
        if pages > 1:
            rs = await asyncio.gather(*[self._get(url, {**params, "page": p}, token) for p in range(2, pages + 1)])
            for rr in rs:
                out.extend(rr.json() or [])
        return out

    # ------------------------------------------------------------------ public data
    async def adjusted_prices(self) -> dict[int, float]:
        c = self.cache.get("adjusted", 3600)
        if c is None:
            r = await self._get(f"{ESI}/markets/prices")
            c = {str(x["type_id"]): {"adj": x.get("adjusted_price") or 0, "avg": x.get("average_price") or 0}
                 for x in r.json()}
            self.cache.set("adjusted", c)
        return {int(k): v for k, v in c.items()}

    async def cost_indices(self) -> dict[int, dict[str, float]]:
        c = self.cache.get("indices", 3600)
        if c is None:
            r = await self._get(f"{ESI}/industry/systems")
            c = {str(x["solar_system_id"]): {ci["activity"]: ci["cost_index"] for ci in x["cost_indices"]}
                 for x in r.json()}
            self.cache.set("indices", c)
        return {int(k): v for k, v in c.items()}

    async def resolve_system(self, name: str) -> dict | None:
        r = await self.client.post(f"{ESI}/universe/ids", json=[name], headers=self._headers())
        if r.status_code != 200:
            return None
        sys = (r.json() or {}).get("systems") or []
        if not sys:
            return None
        sid = sys[0]["id"]
        info = (await self._get(f"{ESI}/universe/systems/{sid}")).json()
        sec = info.get("security_status", 0)
        band = "high" if sec >= 0.45 else ("low" if sec > 0.0 else "null")
        return {"system_id": sid, "name": info.get("name", name), "security": round(sec, 2), "band": band}

    async def market_history(self, region_id: int, type_id: int) -> dict:
        key = f"hist:{region_id}:{type_id}"
        c = self.cache.get(key, 12 * 3600)
        if c is None:
            r = await self._get(f"{ESI}/markets/{region_id}/history", {"type_id": type_id})
            rows = r.json() if r.status_code == 200 else []
            rows = rows[-30:]
            vol = sum(x["volume"] for x in rows) / 30 if rows else 0
            avg = sum(x["average"] for x in rows[-7:]) / max(1, len(rows[-7:])) if rows else 0
            c = {"daily_volume": vol, "avg_price_7d": avg, "days": len(rows)}
            self.cache.set(key, c)
        return c

    async def histories(self, region_id: int, type_ids, progress=None) -> dict[int, dict]:
        type_ids = list(type_ids)
        out = {}
        done = 0

        async def one(t):
            nonlocal done
            try:
                out[t] = await self.market_history(region_id, t)
            except Exception:
                out[t] = {"daily_volume": 0, "avg_price_7d": 0, "days": 0}
            done += 1
            if progress and done % 20 == 0:
                progress(f"Historique de marché : {done}/{len(type_ids)}")

        await asyncio.gather(*[one(t) for t in type_ids])
        self.cache.flush()
        return out

    async def type_info(self, type_id: int) -> dict:
        key = f"type:{type_id}"
        c = self.cache.get(key, 30 * 86400)
        if c is None:
            r = await self._get(f"{ESI}/universe/types/{type_id}")
            j = r.json() if r.status_code == 200 else {}
            c = {"packaged_volume": j.get("packaged_volume") or j.get("volume") or 0}
            self.cache.set(key, c)
        return c

    # ------------------------------------------------------------------ market prices
    async def market_prices(self, market: dict, type_ids) -> dict[int, dict]:
        """Renvoie {type_id: {"sell": min_vente, "buy": max_achat, "sell_vol":…, "buy_vol":…}}."""
        type_ids = sorted(set(int(t) for t in type_ids))
        if market.get("kind") == "structure":
            return await self._structure_prices(market, type_ids)
        try:
            return await self._fuzzwork_prices(market, type_ids)
        except Exception:
            return await self._esi_station_prices(market, type_ids)

    async def _fuzzwork_prices(self, market, type_ids):
        station = market["station_id"]
        out, missing = {}, []
        for t in type_ids:
            c = self.cache.get(f"fz:{station}:{t}", 900)
            if c is not None:
                out[t] = c
            else:
                missing.append(t)

        async def chunk(ids):
            async with self.sem:
                r = await self.client.get(FUZZ, params={"station": station, "types": ",".join(map(str, ids))},
                                          headers={"User-Agent": self.settings_getter().get("user_agent", "")})
            r.raise_for_status()
            return r.json()

        chunks = [missing[i:i + 200] for i in range(0, len(missing), 200)]
        results = await asyncio.gather(*[chunk(c) for c in chunks])
        for res in results:
            for k, v in res.items():
                d = {"sell": float(v["sell"]["min"] or 0), "buy": float(v["buy"]["max"] or 0),
                     "sell_vol": float(v["sell"]["volume"] or 0), "buy_vol": float(v["buy"]["volume"] or 0)}
                out[int(k)] = d
                self.cache.set(f"fz:{station}:{k}", d)
        self.cache.flush()
        return out

    def _aggregate(self, orders, type_ids, location_id=None):
        wanted = set(type_ids)
        agg = {}
        for o in orders:
            t = o["type_id"]
            if t not in wanted or (location_id and o.get("location_id") != location_id):
                continue
            a = agg.setdefault(t, {"sell": 0.0, "buy": 0.0, "sell_vol": 0.0, "buy_vol": 0.0})
            if o["is_buy_order"]:
                a["buy"] = max(a["buy"], o["price"])
                a["buy_vol"] += o["volume_remain"]
            else:
                a["sell"] = o["price"] if a["sell"] == 0 else min(a["sell"], o["price"])
                a["sell_vol"] += o["volume_remain"]
        return agg

    async def _esi_station_prices(self, market, type_ids):
        key = f"region_orders:{market['region_id']}"
        orders = getattr(self, "_region_mem", {}).get(key)
        if not orders or time.time() - orders[0] > 600:
            data = await self._get_paged(f"{ESI}/markets/{market['region_id']}/orders", {"order_type": "all"})
            self._region_mem = {key: (time.time(), data)}
            orders = self._region_mem[key]
        return self._aggregate(orders[1], type_ids, market["station_id"])

    async def _structure_prices(self, market, type_ids):
        token = await self.access_token(int(market.get("character_id") or 0))
        if not token:
            raise EsiError(f"Marché {market.get('name')} : connecte un personnage qui a accès à la structure.")
        mem = getattr(self, "_struct_mem", {})
        key = market["structure_id"]
        if key not in mem or time.time() - mem[key][0] > 600:
            data = await self._get_paged(f"{ESI}/markets/structures/{market['structure_id']}", token=token)
            mem[key] = (time.time(), data)
            self._struct_mem = mem
        return self._aggregate(mem[key][1], type_ids)

    # ------------------------------------------------------------------ SSO
    def _load_tokens(self):
        if os.path.exists(TOKENS_PATH):
            try:
                with open(TOKENS_PATH, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass
        return {}

    def _save_tokens(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TOKENS_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.tokens, fh, indent=2)

    def login_url(self) -> str:
        s = self.settings_getter()
        if not s.get("esi_client_id"):
            raise EsiError("Renseigne d'abord le Client ID de ton application EVE dans Réglages.")
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        self._pkce[state] = verifier
        q = {"response_type": "code", "redirect_uri": s["callback_url"], "client_id": s["esi_client_id"],
             "scope": " ".join(SCOPES), "state": state, "code_challenge": challenge,
             "code_challenge_method": "S256"}
        return SSO_AUTH + "?" + urllib.parse.urlencode(q)

    async def _token_request(self, data: dict) -> dict:
        s = self.settings_getter()
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Host": "login.eveonline.com"}
        if s.get("esi_client_secret"):
            basic = base64.b64encode(f"{s['esi_client_id']}:{s['esi_client_secret']}".encode()).decode()
            headers["Authorization"] = f"Basic {basic}"
        else:
            data = {**data, "client_id": s["esi_client_id"]}
        r = await self.client.post(SSO_TOKEN, data=data, headers=headers)
        if r.status_code != 200:
            raise EsiError(f"SSO : {r.status_code} {r.text[:200]}")
        return r.json()

    @staticmethod
    def _jwt_payload(tok: str) -> dict:
        part = tok.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))

    async def handle_callback(self, code: str, state: str) -> dict:
        verifier = self._pkce.pop(state, None)
        if not verifier:
            raise EsiError("État SSO inconnu : relance la connexion depuis l'outil.")
        j = await self._token_request({"grant_type": "authorization_code", "code": code,
                                       "code_verifier": verifier})
        p = self._jwt_payload(j["access_token"])
        cid = int(p["sub"].split(":")[-1])
        info = (await self._get(f"{ESI}/characters/{cid}")).json()
        scp = p.get("scp") or []
        self.tokens[str(cid)] = {"name": p.get("name"), "access": j["access_token"],
                                 "refresh": j["refresh_token"], "exp": time.time() + int(j.get("expires_in", 1199)) - 60,
                                 "corporation_id": info.get("corporation_id"), "alliance_id": info.get("alliance_id"),
                                 "scopes": [scp] if isinstance(scp, str) else list(scp), "added": time.time()}
        await self._affiliation_names(cid)
        self._save_tokens()
        return {"character_id": cid, "name": p.get("name")}

    async def _affiliation_names(self, cid):
        t = self.tokens.get(str(cid))
        if not t:
            return
        ids = [i for i in (t.get("corporation_id"), t.get("alliance_id")) if i]
        if not ids:
            return
        try:
            r = await self.client.post(f"{ESI}/universe/names", json=ids, headers=self._headers())
            for x in r.json() if r.status_code == 200 else []:
                if x["category"] == "corporation":
                    t["corporation_name"] = x["name"]
                elif x["category"] == "alliance":
                    t["alliance_name"] = x["name"]
        except Exception:
            pass

    async def refresh_affiliations(self):
        """Met à jour corpo/alliance de chaque perso (changement de corpo, etc.)."""
        ids = [int(k) for k in self.tokens]
        if not ids:
            return
        try:
            r = await self.client.post(f"{ESI}/characters/affiliation", json=ids, headers=self._headers())
            for a in r.json() if r.status_code == 200 else []:
                t = self.tokens[str(a["character_id"])]
                t["corporation_id"], t["alliance_id"] = a.get("corporation_id"), a.get("alliance_id")
            for cid in ids:
                await self._affiliation_names(cid)
            self._save_tokens()
        except Exception:
            pass

    async def access_token(self, cid: int) -> str | None:
        t = self.tokens.get(str(cid))
        if not t:
            return None
        if time.time() < t["exp"]:
            return t["access"]
        try:
            j = await self._token_request({"grant_type": "refresh_token", "refresh_token": t["refresh"]})
        except EsiError:
            t["broken"] = True
            self._save_tokens()
            raise EsiError(f"{t.get('name')} : connexion expirée ou révoquée, reconnecte ce personnage.")
        t.pop("broken", None)
        t.update(access=j["access_token"], refresh=j.get("refresh_token", t["refresh"]),
                 exp=time.time() + int(j.get("expires_in", 1199)) - 60)
        self._save_tokens()
        return t["access"]

    def scopes_of(self, t) -> list:
        if t.get("scopes"):
            return t["scopes"]
        try:   # anciens jetons : on relit les permissions dans le JWT
            scp = self._jwt_payload(t["access"]).get("scp") or []
            return [scp] if isinstance(scp, str) else list(scp)
        except Exception:
            return []

    def characters(self):
        out = []
        for k, v in self.tokens.items():
            granted = self.scopes_of(v)
            out.append({"character_id": int(k), "name": v["name"], "corporation_id": v.get("corporation_id"),
                        "corporation_name": v.get("corporation_name"), "alliance_id": v.get("alliance_id"),
                        "alliance_name": v.get("alliance_name"), "broken": bool(v.get("broken")),
                        "missing_scopes": [s for s in SCOPES if s not in granted]})
        return sorted(out, key=lambda c: c["name"] or "")

    def remove_character(self, cid: int):
        self.tokens.pop(str(cid), None)
        self._save_tokens()

    async def char_assets(self, cid):
        tok = await self.access_token(cid)
        return await self._get_paged(f"{ESI}/characters/{cid}/assets", token=tok)

    async def corp_assets(self, cid):
        tok = await self.access_token(cid)
        corp = self.tokens[str(cid)]["corporation_id"]
        return await self._get_paged(f"{ESI}/corporations/{corp}/assets", token=tok)

    async def corp_divisions(self, cid):
        tok = await self.access_token(cid)
        corp = self.tokens[str(cid)]["corporation_id"]
        r = await self._get(f"{ESI}/corporations/{corp}/divisions", token=tok)
        return (r.json() or {}).get("hangar", []) if r.status_code == 200 else []

    async def char_blueprints(self, cid):
        tok = await self.access_token(cid)
        return await self._get_paged(f"{ESI}/characters/{cid}/blueprints", token=tok)

    async def char_jobs(self, cid):
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/industry/jobs", {"include_completed": "false"}, token=tok)
        return r.json() if r.status_code == 200 else []

    async def location_names(self, ids, known=None) -> dict[int, str]:
        """Noms des stations (public), structures (accès docking requis) et systèmes."""
        known = dict(known or {})
        todo = [int(i) for i in set(ids) if int(i) not in known]
        systems = []

        async def station(i):
            r = await self._get(f"{ESI}/universe/stations/{i}")
            if r.status_code == 200:
                known[i] = r.json().get("name", f"Station {i}")

        async def structure(i):
            for ch in self.characters():
                try:
                    tok = await self.access_token(ch["character_id"])
                    r = await self.client.get(f"{ESI}/universe/structures/{i}", headers=self._headers(tok))
                    if r.status_code == 200:
                        known[i] = r.json().get("name", f"Structure {i}")
                        return
                except Exception:
                    continue
            known[i] = f"Structure {i} (pas d'accès docking)"

        tasks = []
        for i in todo:
            if 60_000_000 <= i < 64_000_000:
                tasks.append(station(i))
            elif i >= 1_000_000_000_000:
                tasks.append(structure(i))
            elif 30_000_000 <= i < 33_000_000:
                systems.append(i)
            else:
                known[i] = f"Emplacement {i}"
        await asyncio.gather(*tasks, return_exceptions=True)
        if systems:
            r = await self.client.post(f"{ESI}/universe/names", json=systems, headers=self._headers())
            if r.status_code == 200:
                for x in r.json():
                    known[x["id"]] = f"Dans l'espace — {x['name']}"
        for i in todo:
            known.setdefault(i, f"Emplacement {i}")
        return known

    async def char_skills(self, cid):
        """Renvoie {"levels": {id: niveau}, "sp": {id: sp}, "total_sp": n}."""
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/skills", token=tok)
        j = r.json() or {}
        sk = j.get("skills", [])
        return {"levels": {s["skill_id"]: s["active_skill_level"] for s in sk},
                "sp": {s["skill_id"]: s.get("skillpoints_in_skill", 0) for s in sk},
                "total_sp": j.get("total_sp", 0)}

    # ------------------------------------------------------------------ carte
    async def system_activity(self) -> dict:
        """Activité de la dernière heure (ESI, mise à jour toutes les heures) : {système: {kills, pods, npc, jumps}}."""
        c = self.cache.get("activity", 600)
        if c is None:
            kills, jumps = await asyncio.gather(self._get(f"{ESI}/universe/system_kills"),
                                                self._get(f"{ESI}/universe/system_jumps"))
            c = {}
            for k in kills.json() or []:
                c[str(k["system_id"])] = {"kills": k.get("ship_kills", 0), "pods": k.get("pod_kills", 0),
                                          "npc": k.get("npc_kills", 0), "jumps": 0}
            for j in jumps.json() or []:
                c.setdefault(str(j["system_id"]), {"kills": 0, "pods": 0, "npc": 0, "jumps": 0})["jumps"] = j.get("ship_jumps", 0)
            self.cache.set("activity", c)
            self.cache.flush()
        return {int(k): v for k, v in c.items()}

    async def sovereignty(self) -> dict:
        """Souveraineté par système : {système: {alliance_id, faction_id, owner}}. Accepte l'ancien format
        (/sovereignty/map) et le nouveau (/sovereignty/systems), y compris enveloppé dans un objet."""
        c = self.cache.get("sov2", 3600)
        if c is None:
            rows = []
            for path in ("/sovereignty/systems", "/sovereignty/map"):
                try:
                    r = await self._get(f"{ESI}{path}")
                except EsiError:
                    continue
                if r.status_code != 200:
                    continue
                j = r.json()
                if isinstance(j, dict):
                    j = j.get("systems") or j.get("items") or j.get("data") or []
                if isinstance(j, list) and j:
                    rows = j
                    break
            c = parse_sov(rows)
            ids = {v["alliance_id"] for v in c.values() if v.get("alliance_id")} | \
                  {v["faction_id"] for v in c.values() if v.get("faction_id")}
            try:
                names = await self.ids_to_names(ids)
            except Exception:
                names = {}
            for v in c.values():
                oid = v.get("alliance_id") or v.get("faction_id")
                v["owner"] = names.get(oid) or (f"Alliance {oid}" if oid else "")
            self.cache.set("sov2", c)
            self.cache.flush()
        return {int(k): v for k, v in c.items()}

    async def evescout(self) -> list:
        c = self.cache.get("evescout", 300)
        if c is None:
            r = await self.client.get("https://api.eve-scout.com/v2/public/signatures", timeout=20,
                                      headers={"User-Agent": self.settings_getter().get("user_agent") or "Cockpit"})
            r.raise_for_status()
            c = r.json()
            self.cache.set("evescout", c)
        return c

    async def char_location(self, cid):
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/location", token=tok)
        loc = r.json() if r.status_code == 200 else {}
        ship = {}
        try:
            rs = await self._get(f"{ESI}/characters/{cid}/ship", token=tok)
            ship = rs.json() if rs.status_code == 200 else {}
        except Exception:
            pass
        return {"system_id": loc.get("solar_system_id"), "ship_type_id": ship.get("ship_type_id"),
                "ship_name": ship.get("ship_name")}

    async def open_info_window(self, cid, target_id):
        """Ouvre la fiche d'un personnage dans le client EVE du personnage connecté."""
        tok = await self.access_token(cid)
        r = await self.client.post(f"{ESI}/ui/openwindow/information", headers=self._headers(tok),
                                   params={"target_id": target_id})
        if r.status_code not in (200, 204):
            if r.status_code == 403:
                raise EsiError("Permission manquante (esi-ui.open_window.v1) : reconnecte ce personnage.")
            raise EsiError(f"EVE a refusé ({r.status_code}) : le personnage doit être connecté en jeu.")

    async def ansiblex(self, cid) -> list[dict]:
        """Ponts Ansiblex visibles par le personnage : recherche des structures dont le nom contient « » »
        (format « SYSTÈME A » SYSTÈME B - nom »), puis lecture de chaque structure."""
        tok = await self.access_token(cid)
        ids = []
        for q in (" » ", "»"):
            r = await self.client.get(f"{ESI}/characters/{cid}/search", headers=self._headers(tok),
                                      params={"categories": "structure", "search": q, "strict": "false"})
            if r.status_code == 403:
                raise EsiError("Permission manquante (esi-search.search_structures.v1) : reconnecte ce personnage.")
            if r.status_code == 200:
                ids = (r.json() or {}).get("structure") or []
                if ids:
                    break
        out = []

        async def one(i):
            try:
                rr = await self._get(f"{ESI}/universe/structures/{i}", token=tok)
                if rr.status_code == 200:
                    j = rr.json()
                    if "»" in (j.get("name") or "") and j.get("type_id") in (None, 35841):
                        out.append({"structure_id": i, "name": j["name"], "system_id": j.get("solar_system_id")})
            except Exception:
                pass

        await asyncio.gather(*[one(i) for i in ids[:600]])
        return out

    async def set_waypoint(self, cid, destination_id, clear=True, first=False):
        tok = await self.access_token(cid)
        r = await self.client.post(f"{ESI}/ui/autopilot/waypoint", headers=self._headers(tok),
                                   params={"destination_id": destination_id, "clear_other_waypoints": str(clear).lower(),
                                           "add_to_beginning": str(first).lower()})
        if r.status_code not in (200, 204):
            if r.status_code == 403:
                raise EsiError("Permission manquante : reconnecte ce personnage (esi-ui.write_waypoint.v1).")
            raise EsiError(f"EVE a refusé ({r.status_code}). Le personnage doit être connecté en jeu.")

    async def contacts(self, cid):
        """Standings du perso, de sa corpo et de son alliance : {"personal": {id: s}, "corp": {...}, "alliance": {...}}."""
        tok = await self.access_token(cid)
        t = self.tokens[str(cid)]
        out = {"personal": {}, "corp": {}, "alliance": {}}
        urls = [("personal", f"{ESI}/characters/{cid}/contacts")]
        if t.get("corporation_id"):
            urls.append(("corp", f"{ESI}/corporations/{t['corporation_id']}/contacts"))
        if t.get("alliance_id"):
            urls.append(("alliance", f"{ESI}/alliances/{t['alliance_id']}/contacts"))
        for key, url in urls:
            try:
                for c in await self._get_paged(url, token=tok):
                    out[key][int(c["contact_id"])] = float(c["standing"])
            except Exception:
                pass   # permission absente : on continue avec ce qu'on a
        return out

    async def char_attributes(self, cid):
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/attributes", token=tok)
        return r.json() if r.status_code == 200 else {}

    async def char_skillqueue(self, cid):
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/skillqueue", token=tok)
        q = {}
        for e in r.json() if r.status_code == 200 else []:
            sk, lvl = e["skill_id"], e["finished_level"]
            if lvl > q.get(sk, (0, None))[0]:
                q[sk] = (lvl, e.get("finish_date"))
        return q

    async def char_fittings(self, cid):
        tok = await self.access_token(cid)
        r = await self._get(f"{ESI}/characters/{cid}/fittings", token=tok)
        if r.status_code != 200:
            raise EsiError("Lecture des fittings impossible : reconnecte ce personnage (nouvelle permission).")
        return r.json()

    async def push_fitting(self, cid, fitting: dict):
        tok = await self.access_token(cid)
        r = await self.client.post(f"{ESI}/characters/{cid}/fittings", json=fitting, headers=self._headers(tok))
        if r.status_code not in (200, 201):
            if r.status_code == 403:
                raise EsiError("Permission manquante : reconnecte ce personnage pour autoriser l'écriture des fittings.")
            raise EsiError(f"Envoi refusé par EVE ({r.status_code}) : {r.text[:200]}")
        return r.json()

    async def resolve_names(self, names: list[str]) -> dict:
        """Noms -> IDs (personnages, corpos, alliances). ESI accepte 500 noms par requête."""
        out = {"characters": [], "corporations": [], "alliances": []}
        for i in range(0, len(names), 500):
            r = await self.client.post(f"{ESI}/universe/ids", json=names[i:i + 500], headers=self._headers())
            if r.status_code == 200:
                j = r.json() or {}
                for k in out:
                    out[k].extend(j.get(k) or [])
        return out

    async def affiliations(self, char_ids: list[int]) -> list:
        out = []
        for i in range(0, len(char_ids), 1000):
            r = await self.client.post(f"{ESI}/characters/affiliation", json=char_ids[i:i + 1000], headers=self._headers())
            if r.status_code == 200:
                out.extend(r.json())
        return out

    async def ids_to_names(self, ids) -> dict[int, str]:
        ids = sorted({int(i) for i in ids if i})
        out = {}
        for i in range(0, len(ids), 1000):
            r = await self.client.post(f"{ESI}/universe/names", json=ids[i:i + 1000], headers=self._headers())
            if r.status_code == 200:
                for x in r.json():
                    out[x["id"]] = x["name"]
        return out
