"""Fits : lecture/écriture du format EFT (copier-coller du jeu et de Pyfa), conversion vers les fittings ESI,
compétences requises et temps d'entraînement.

Format EFT :
    [Vexor, Vexor DPS]
    Drone Damage Amplifier II          <- modules (l'ordre des sections n'a pas d'importance : le slot vient du SDE)
    Heavy Neutron Blaster II, Void M   <- module, munition chargée
    [Empty Med slot]
    Hammerhead II x5                   <- drones / cargo : « nom xQuantité »
"""
from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict

HEADER = re.compile(r"^\[\s*([^,\]]+?)\s*,\s*(.*?)\s*\]\s*$")
QTY = re.compile(r"^(.*?)\s+x\s?(\d[\d\s.,]*)$", re.IGNORECASE)
SLOT_ORDER = ["low", "med", "high", "rig", "subsystem", "service", "drone", "fighter", "charge", "cargo"]
SLOT_LABELS = {"high": "Slots hauts", "med": "Slots moyens", "low": "Slots bas", "rig": "Rigs",
               "subsystem": "Sous-systèmes", "service": "Services", "drone": "Drones", "fighter": "Chasseurs",
               "charge": "Munitions chargées", "cargo": "Soute"}
ESI_FLAG = {"high": "HiSlot", "med": "MedSlot", "low": "LoSlot", "rig": "RigSlot", "subsystem": "SubSystemSlot",
            "service": "ServiceSlot"}
FLAG_SLOT = {v: k for k, v in ESI_FLAG.items()}

ATTR_NAMES = {164: "charisma", 165: "intelligence", 166: "memory", 167: "perception", 168: "willpower"}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def _item_slot(sde, tid, has_qty):
    sl = sde.slot.get(tid)
    if sl:
        return sl
    cat = sde.category_name(tid)
    if cat == "Drone":
        return "drone"
    if cat == "Fighter":
        return "fighter"
    return "cargo"


def _num(s):
    return int(re.sub(r"[\s.,]", "", s) or 0)


def parse_eft(text: str, sde) -> list[dict]:
    """Analyse un ou plusieurs fits EFT. Renvoie [{ship_type_id, name, items, unknown}]."""
    fits, cur = [], None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = HEADER.match(line)
        if m and not line.lower().startswith("[empty"):
            ship = sde.find_any(m.group(1))
            cur = {"ship_type_id": ship, "ship_name_raw": m.group(1), "name": m.group(2) or m.group(1),
                   "items": [], "unknown": []}
            if not ship:
                cur["unknown"].append(f"Vaisseau inconnu : {m.group(1)}")
            fits.append(cur)
            continue
        if cur is None or line.lower().startswith("[empty"):
            continue
        line = re.sub(r"\s*/\s*offline$", "", line, flags=re.IGNORECASE)
        qty = None
        mq = QTY.match(line)
        if mq and not sde.find_any(line):
            line, qty = mq.group(1).strip(), _num(mq.group(2))
        charge = None
        tid = sde.find_any(line)
        if not tid and ", " in line:
            left, right = line.split(", ", 1)
            tid, charge = sde.find_any(left), sde.find_any(right)
            if tid and not charge:
                cur["unknown"].append(f"Munition inconnue : {right}")
        if not tid:
            cur["unknown"].append(line)
            continue
        slot = _item_slot(sde, tid, qty is not None)
        item = {"type_id": tid, "qty": qty or 1, "slot": slot}
        if charge:
            item["charge"] = charge
        cur["items"].append(item)
        if charge:
            cur["items"].append({"type_id": charge, "qty": 1, "slot": "charge"})
    for f in fits:
        f["items"] = merge_items(f["items"])
    return [f for f in fits if f["ship_type_id"]] + [f for f in fits if not f["ship_type_id"]]


def merge_items(items):
    """Regroupe les lignes identiques (même objet, même slot, même munition)."""
    agg = defaultdict(int)
    order = []
    for it in items:
        k = (it["type_id"], it["slot"], it.get("charge"))
        if k not in agg:
            order.append(k)
        agg[k] += int(it["qty"])
    out = []
    for t, s, c in order:
        d = {"type_id": t, "slot": s, "qty": agg[(t, s, c)]}
        if c:
            d["charge"] = c
        out.append(d)
    return out


def to_eft(fit, sde, lang="en") -> str:
    """Fit -> texte EFT (noms anglais par défaut : c'est ce que Pyfa et la plupart des outils attendent)."""
    nm = (lambda t: sde.name(t, lang))
    lines = [f"[{nm(fit['ship_type_id'])}, {fit['name']}]"]
    by_slot = defaultdict(list)
    for it in fit["items"]:
        by_slot[it["slot"]].append(it)
    for sl in ("low", "med", "high", "rig", "subsystem", "service"):
        for it in by_slot.get(sl, []):
            for _ in range(it["qty"]):
                lines.append(nm(it["type_id"]) + (f", {nm(it['charge'])}" if it.get("charge") else ""))
        lines.append("")
    for sl in ("drone", "fighter"):
        for it in by_slot.get(sl, []):
            lines.append(f"{nm(it['type_id'])} x{it['qty']}")
    lines.append("")
    for it in by_slot.get("cargo", []):
        lines.append(f"{nm(it['type_id'])} x{it['qty']}")
    return "\n".join(lines).strip() + "\n"


def to_esi_fitting(fit, sde, description=""):
    items, counters = [], defaultdict(int)
    for it in fit["items"]:
        sl = it["slot"]
        if sl in ESI_FLAG:
            for _ in range(it["qty"]):
                items.append({"type_id": it["type_id"], "flag": f"{ESI_FLAG[sl]}{counters[sl]}", "quantity": 1})
                counters[sl] += 1
        elif sl == "drone":
            items.append({"type_id": it["type_id"], "flag": "DroneBay", "quantity": it["qty"]})
        elif sl == "fighter":
            items.append({"type_id": it["type_id"], "flag": "FighterBay", "quantity": it["qty"]})
        else:
            items.append({"type_id": it["type_id"], "flag": "Cargo", "quantity": it["qty"]})
    return {"name": fit["name"][:50], "description": (description or fit.get("notes") or "")[:500] or fit["name"][:50],
            "ship_type_id": fit["ship_type_id"], "items": items}


def from_esi_fitting(f, sde):
    items = []
    for it in f.get("items") or []:
        flag = str(it.get("flag", ""))
        base = re.sub(r"\d+$", "", flag)
        if base in FLAG_SLOT:
            slot = FLAG_SLOT[base]
        elif flag == "DroneBay":
            slot = "drone"
        elif flag == "FighterBay":
            slot = "fighter"
        else:
            slot = "cargo"
        items.append({"type_id": int(it["type_id"]), "qty": int(it.get("quantity") or 1), "slot": slot})
    return {"ship_type_id": int(f["ship_type_id"]), "name": f.get("name") or "Fit", "items": merge_items(items),
            "unknown": [], "notes": f.get("description") or ""}


def new_fit(parsed, role="DPS", notes=""):
    return {"id": uuid.uuid4().hex[:10], "name": parsed["name"], "ship_type_id": parsed["ship_type_id"],
            "items": parsed["items"], "role": role, "notes": notes or parsed.get("notes", "")}


# ---------------------------------------------------------------------- compétences
def sp_for_level(rank: int, level: int) -> int:
    if level <= 0:
        return 0
    return math.ceil(250 * rank * 32 ** ((level - 1) / 2))


def requirements(type_ids, sde) -> dict[int, int]:
    """Compétences requises (avec tous les prérequis) -> niveau minimal."""
    need: dict[int, int] = {}
    stack = [(s, l) for t in set(type_ids) for s, l in sde.req_skills.get(t, [])]
    while stack:
        sk, lvl = stack.pop()
        if need.get(sk, 0) >= lvl:
            continue
        need[sk] = lvl
        stack.extend(sde.req_skills.get(sk, []))
    return need


def fit_type_ids(fit):
    return [fit["ship_type_id"]] + [it["type_id"] for it in fit["items"] if it["slot"] != "cargo"]


def check_pilot(need: dict[int, int], char: dict, sde) -> dict:
    """char = {"levels": {skill: niveau}, "sp": {skill: sp}, "attrs": {...}, "queue": {skill: (niveau, fin)}}"""
    levels, sps, attrs = char.get("levels", {}), char.get("sp", {}), char.get("attrs") or {}
    queue = char.get("queue", {})
    missing, total = [], 0.0
    for sk, lvl in sorted(need.items(), key=lambda x: sde.name(x[0])):
        have = int(levels.get(sk, 0))
        if have >= lvl:
            continue
        rank, prim, sec = sde.skill_meta.get(sk, (1, 165, 166))
        rate = (attrs.get(ATTR_NAMES.get(prim, "intelligence"), 20) + attrs.get(ATTR_NAMES.get(sec, "memory"), 20) / 2)
        cur_sp = max(int(sps.get(sk, 0)), sp_for_level(rank, have))
        sp_needed = max(0, sp_for_level(rank, lvl) - cur_sp)
        secs = sp_needed / max(rate, 1) * 60
        q = queue.get(sk)
        queued = q if q and q[0] >= lvl else None
        if not queued:
            total += secs
        missing.append({"skill_id": sk, "name": sde.name(sk), "name_en": sde.name_en(sk), "have": have, "need": lvl,
                        "time_s": secs, "queued_until": queued[1] if queued else None})
    return {"can_fly": not missing, "missing": missing, "train_time_s": total,
            "only_queued": bool(missing) and all(m["queued_until"] for m in missing)}


def _depth(sk, sde, memo, guard=0):
    if sk in memo:
        return memo[sk]
    reqs = sde.req_skills.get(sk, [])
    memo[sk] = 0 if not reqs or guard > 20 else 1 + max(_depth(r, sde, memo, guard + 1) for r, _ in reqs)
    return memo[sk]


def skill_plan_text(missing, sde) -> str:
    """Liste « Compétence Niveau » (un niveau par ligne), prérequis d'abord, en anglais."""
    lines, memo = [], {}
    for m in sorted(missing, key=lambda m: (_depth(m["skill_id"], sde, memo), m["name_en"])):
        for lvl in range(m["have"] + 1, m["need"] + 1):
            lines.append(f"{m['name_en']} {ROMAN[lvl]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------- import de fichiers (XML du jeu / Pyfa, EFT)
XML_SLOTS = {"low": "low", "med": "med", "mid": "med", "hi": "high", "high": "high", "rig": "rig",
             "subsystem": "subsystem", "service": "service"}


def parse_xml(text: str, sde) -> list[dict]:
    """Fichier XML exporté par la fenêtre de gestion des fits d'EVE (ou par Pyfa)."""
    import xml.etree.ElementTree as ET
    low = text[:2000].lower()
    if "<!doctype" in low or "<!entity" in low:
        raise ValueError("Fichier XML refusé (déclarations DOCTYPE/ENTITY non autorisées).")
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    fits = []
    for f in root.iter("fitting"):
        name = (f.get("name") or "Fit").strip()
        ship_el = f.find("shipType")
        ship_raw = (ship_el.get("value") if ship_el is not None else "") or ""
        desc_el = f.find("description")
        cur = {"ship_type_id": sde.find_any(ship_raw), "ship_name_raw": ship_raw, "name": name,
               "items": [], "unknown": [], "notes": ((desc_el.get("value") if desc_el is not None else "") or "")[:500]}
        if not cur["ship_type_id"]:
            cur["unknown"].append(f"Vaisseau inconnu : {ship_raw}")
        for hw in f.iter("hardware"):
            tname = (hw.get("type") or "").strip()
            slot_raw = (hw.get("slot") or "cargo").strip().lower()
            try:
                qty = int(float(hw.get("qty") or 1))
            except ValueError:
                qty = 1
            tid = sde.find_any(tname)
            if not tid:
                cur["unknown"].append(tname or "(vide)")
                continue
            first = slot_raw.split()[0] if slot_raw else "cargo"
            if first in XML_SLOTS:
                slot = XML_SLOTS[first]
            elif "drone" in slot_raw:
                slot = "drone"
            elif "fighter" in slot_raw:
                slot = "fighter"
            else:
                slot = "cargo"
            cur["items"].append({"type_id": tid, "qty": max(1, qty), "slot": slot})
        cur["items"] = merge_items(cur["items"])
        fits.append(cur)
    return fits


def parse_any(text: str, sde) -> tuple[str, list[dict]]:
    """Détecte le format : XML (jeu/Pyfa) ou EFT (un ou plusieurs fits). Renvoie (format, fits)."""
    t = (text or "").lstrip("\ufeff").strip()
    if t.startswith("<") or "<fitting" in t[:5000]:
        return "xml", parse_xml(t, sde)
    return "eft", parse_eft(t, sde)


ROLE_BY_GROUP = [
    (("logistics", "force auxiliary"), "Logistique"),
    (("interceptor", "interdictor", "heavy interdiction"), "Tackle"),
    (("command ship", "command destroyer"), "Boosts"),
    (("recon", "electronic attack"), "Ewar"),
    (("stealth bomber",), "Bombardier"),
    (("covert ops", "expedition"), "Éclaireur"),
    (("carrier", "dreadnought", "titan", "supercarrier", "lancer"), "Capital"),
]


NAME_ROLES = [
    (r"\b(logi|logistique|heal|soin|reps?)\b", "Logistique"),
    (r"\b(tackle|tackler|point|scram|bulle|bubble|dictor|hic)\b", "Tackle"),
    (r"\b(ewar|jam|ecm|damp|tp|painter|neut|recon)\b", "Ewar"),
    (r"\b(boost|booster|links?|command)\b", "Boosts"),
    (r"\b(scout|eclaireur|éclaireur|cloak|cyno)\b", "Éclaireur"),
    (r"\b(fc)\b", "FC"),
    (r"\b(bomb|bomber|bombardier)\b", "Bombardier"),
    (r"\b(dps|brawl|kite|sniper)\b", "DPS"),
]


def guess_role(sde, ship_type_id, name: str = "") -> str:
    """Rôle deviné : d'abord les mots du nom du fit (« Logi », « Tackle »…), sinon le type de vaisseau."""
    low = (name or "").lower()
    for rx, role in NAME_ROLES:
        if re.search(rx, low):
            return role
    g = sde.group_name_en(ship_type_id).lower() if ship_type_id else ""
    for keys, role in ROLE_BY_GROUP:
        if any(k in g for k in keys):
            return role
    return "DPS"


PREFIX = [re.compile(r"^\s*\[([^\]]{1,40})\]\s*(.+)$"), re.compile(r"^\s*([^-–|:]{1,40}?)\s*[-–|:]\s+(.+)$")]


def split_prefix(name: str) -> tuple[str | None, str]:
    """« [Vexor] DPS » ou « Vexor - DPS » -> ("Vexor", "DPS"). Sans préfixe -> (None, nom)."""
    for rx in PREFIX:
        m = rx.match(name or "")
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return None, name


def fit_signature(f) -> tuple:
    return (f["ship_type_id"], tuple(sorted((i["type_id"], i["slot"], i["qty"]) for i in f["items"])))
