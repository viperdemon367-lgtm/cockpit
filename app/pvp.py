"""Intel PvP : scan du local (affiliations + zKillboard) et analyse de D-scan."""
from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict

import httpx

ZKB = "https://zkillboard.com/api/stats/{kind}ID/{id}/"

# groupes de vaisseaux (noms anglais du SDE) -> alerte affichée
THREATS = {
    "Interdictor": "Bulles (interdicteur)",
    "Heavy Interdiction Cruiser": "Bulles / point infini (HIC)",
    "Force Recon Ship": "Cyno camouflé possible (recon)",
    "Combat Recon Ship": "Recon (neut / brouillage)",
    "Black Ops": "Black Ops (pont de saut camouflé)",
    "Stealth Bomber": "Bombardiers",
    "Electronic Attack Ship": "Brouillage (EAF)",
    "Logistics": "Logistique (soins)",
    "Logistics Frigate": "Logistique (soins)",
    "Force Auxiliary": "Capital de soins (FAX)",
    "Command Ship": "Boosts de flotte",
    "Command Destroyer": "Boosts / MJFG",
    "Dreadnought": "Capitaux (dread)",
    "Lancer Dreadnought": "Capitaux (dread)",
    "Carrier": "Capitaux (carrier)",
    "Supercarrier": "SUPERCAPITAUX",
    "Titan": "SUPERCAPITAUX (titan)",
    "Mobile Warp Disruptor": "Bulle posée",
    "Cynosural Fields": "CYNO ALLUMÉ",
    "Cynosural Generator Array": "Générateur de cyno",
    "Marauder": "Marauders",
    "Strategic Cruiser": "T3 (strategic cruisers)",
}
NON_SHIP_KEEP = {"Mobile Warp Disruptor", "Cynosural Fields", "Cynosural Generator Array"}
CLASS_ORDER = ["Capitaux", "Cuirassés", "Croiseurs de combat", "Croiseurs", "Destroyers", "Frégates",
               "Industriels", "Capsules & navettes", "Autres vaisseaux"]


def ship_class(group: str) -> str:
    g = group.lower()
    if any(k in g for k in ("titan", "supercarrier", "carrier", "dreadnought", "force auxiliary", "capital industrial",
                            "freighter", "lancer")):
        return "Capitaux"
    if any(k in g for k in ("battleship", "black ops", "marauder")):
        return "Cuirassés"
    if "battlecruiser" in g or "command ship" in g:
        return "Croiseurs de combat"
    if any(k in g for k in ("cruiser", "recon", "logistics", "strategic")) and "frigate" not in g:
        return "Croiseurs"
    if "destroyer" in g or "interdictor" in g:
        return "Destroyers"
    if any(k in g for k in ("frigate", "interceptor", "bomber", "covert ops", "electronic attack", "corvette")):
        return "Frégates"
    if any(k in g for k in ("industrial", "transport", "hauler", "mining barge", "exhumer", "blockade")):
        return "Industriels"
    if any(k in g for k in ("capsule", "shuttle")):
        return "Capsules & navettes"
    return "Autres vaisseaux"


def _distance_km(s: str):
    s = s.strip().lower().replace("\u00a0", " ")
    m = re.match(r"^([\d\s.,]+)\s*(km|m|au|ua)$", s)
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    # « 1,234 km » (EN) ou « 1 234 km » / « 1,5 UA » (FR)
    if m.group(2) in ("au", "ua"):
        val = float(raw.replace(",", "."))
        return val * 149_597_870.7
    raw = raw.replace(",", "").replace(".", "") if re.search(r"[.,]\d{3}(?!\d)", raw) else raw.replace(",", ".")
    try:
        val = float(raw)
    except ValueError:
        return None
    return val / 1000 if m.group(2) == "m" else val


def parse_dscan(text: str, sde, adjusted: dict, grid_km: float = 10_000):
    ships = defaultdict(lambda: {"count": 0, "on_grid": 0})
    other = defaultdict(int)
    unknown = 0
    has_distance = False
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        cols = [c.strip() for c in raw.split("\t")]
        tid, dist = None, None
        for c in cols:
            if c.isdigit() and int(c) in sde.types and tid is None:
                tid = int(c)
        if tid is None:
            for c in reversed(cols):
                t = sde.find_any(c) if c else None
                if t:
                    tid = t
                    break
        for c in cols:
            d = _distance_km(c)
            if d is not None:
                dist, has_distance = d, True
        if tid is None:
            unknown += 1
            continue
        cat = sde.category_name(tid)
        grp = sde.group_name_en(tid)
        if cat == "Ship" or grp in NON_SHIP_KEEP:
            e = ships[tid]
            e["count"] += 1
            if dist is not None and dist <= grid_km:
                e["on_grid"] += 1
        else:
            other[grp or cat or "?"] += 1
    rows, classes, threats = [], defaultdict(int), defaultdict(int)
    total_value = 0.0
    for tid, e in ships.items():
        grp = sde.group_name_en(tid)
        cls = "Déployables" if grp in NON_SHIP_KEEP else ship_class(grp)
        val = ((adjusted.get(tid) or {}).get("avg") or 0) * e["count"]
        total_value += val
        classes[cls] += e["count"]
        if grp in THREATS:
            threats[THREATS[grp]] += e["count"]
        rows.append({"type_id": tid, "name": sde.name(tid), "group": sde.group_name(tid), "class": cls,
                     "count": e["count"], "on_grid": e["on_grid"], "value": val, "threat": THREATS.get(grp)})
    rows.sort(key=lambda r: (-r["count"], r["name"]))
    order = {c: i for i, c in enumerate(CLASS_ORDER + ["Déployables"])}
    return {
        "ships": rows, "total_ships": sum(r["count"] for r in rows if r["class"] != "Déployables"),
        "on_grid": sum(r["on_grid"] for r in rows if r["class"] != "Déployables"), "has_distance": has_distance,
        "classes": sorted([{"class": k, "count": v} for k, v in classes.items()], key=lambda x: order.get(x["class"], 99)),
        "threats": sorted([{"label": k, "count": v} for k, v in threats.items()], key=lambda x: -x["count"]),
        "estimated_value": total_value, "other": dict(sorted(other.items(), key=lambda x: -x[1])[:12]),
        "unknown_lines": unknown,
    }


class ZKill:
    """Client zKillboard poli : User-Agent identifié, peu de requêtes simultanées, cache 1 h."""

    def __init__(self, client: httpx.AsyncClient, ua_getter, cache):
        self.client, self.ua, self.cache = client, ua_getter, cache
        self.sem = asyncio.Semaphore(3)

    async def stats(self, kind: str, eid: int) -> dict:
        key = f"zkb:{kind}:{eid}"
        c = self.cache.get(key, 3600)
        if c is not None:
            return c
        async with self.sem:
            try:
                r = await self.client.get(ZKB.format(kind=kind, id=eid), timeout=20,
                                          headers={"User-Agent": self.ua(), "Accept-Encoding": "gzip"})
                j = r.json() if r.status_code == 200 else {}
            except Exception:
                j = {}
            await asyncio.sleep(0.15)
        c = summarize_zkb(j if isinstance(j, dict) else {})
        self.cache.set(key, c)
        return c


def summarize_zkb(j: dict) -> dict:
    top_ships = []
    for tl in j.get("topLists") or []:
        if tl.get("type") in ("shipType", "ship"):
            for v in (tl.get("values") or [])[:5]:
                tid = v.get("shipTypeID") or v.get("id")
                if tid:
                    top_ships.append({"type_id": int(tid), "name": v.get("shipName") or v.get("name") or "",
                                      "kills": v.get("kills", 0)})
    active = j.get("activepvp") or {}
    kills_7d = (active.get("kills") or {}).get("count", 0) if isinstance(active.get("kills"), dict) else 0
    destroyed, lost = j.get("shipsDestroyed") or 0, j.get("shipsLost") or 0
    solo = j.get("soloKills") or 0
    return {
        "found": bool(j), "kills": destroyed, "losses": lost,
        "isk_destroyed": j.get("iskDestroyed") or 0, "isk_lost": j.get("iskLost") or 0,
        "danger": j.get("dangerRatio"), "gang": j.get("gangRatio"),
        "solo_pct": round(solo * 100 / destroyed) if destroyed else None,
        "kills_7d": kills_7d, "top_ships": top_ships[:3],
        "efficiency": round((j.get("iskDestroyed") or 0) * 100 / max(1, (j.get("iskDestroyed") or 0) + (j.get("iskLost") or 0))),
        "time": time.time(),
    }


def threat_level(st: dict) -> str:
    if not st.get("found") or not st.get("kills"):
        return "inconnu"
    d, k7 = st.get("danger") or 0, st.get("kills_7d") or 0
    if d >= 75 and k7 >= 5:
        return "très dangereux"
    if d >= 60 or k7 >= 10:
        return "dangereux"
    if d >= 40:
        return "moyen"
    return "faible"


# ---------------------------------------------------------------------- standings
STANDING_LABELS = {"member": "corpo / alliance", "excellent": "excellent (+10)", "good": "bon (+5)",
                   "neutral": "neutre", "bad": "mauvais (-5)", "terrible": "terrible (-10)"}


def merge_standings(per_char: list[dict]) -> dict:
    """Fusionne les standings de plusieurs persos. En cas de désaccord, on garde le plus hostile (prudence)."""
    out = {"personal": {}, "corp": {}, "alliance": {}}
    for st in per_char:
        for k in out:
            for i, v in (st.get(k) or {}).items():
                i = int(i)
                out[k][i] = min(out[k].get(i, v), v)
    return out


def classify(char_id, corp_id, alliance_id, standings: dict, my_corps: set, my_alliances: set):
    """Standing d'un pilote vu par toi, comme en jeu : perso > corpo > alliance, et pour la cible
    le plus précis d'abord (le pilote, puis sa corpo, puis son alliance)."""
    if corp_id in my_corps or (alliance_id and alliance_id in my_alliances):
        return "member", 10.0
    value = None
    for src in ("personal", "corp", "alliance"):
        table = standings.get(src) or {}
        for target in (char_id, corp_id, alliance_id):
            if target and target in table:
                value = table[target]
                break
        if value is not None:
            break
    if value is None or value == 0:
        return "neutral", 0.0
    if value > 5:
        return "excellent", value
    if value > 0:
        return "good", value
    if value >= -5:
        return "bad", value
    return "terrible", value
