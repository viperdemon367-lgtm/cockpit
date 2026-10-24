"""Chargement du Static Data Export (SDE) officiel de CCP (format JSON Lines).

Source : https://developers.eveonline.com/static-data/
Le zip est téléchargé une fois, parsé, puis mis en cache dans data/sde.pickle.
Une vérification du numéro de build permet la mise à jour automatique après un patch.
"""
from __future__ import annotations

import io
import json
import os
import pickle
import zipfile
from dataclasses import dataclass, field

import httpx

SDE_ZIP_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
SDE_LATEST_URL = "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"

from .paths import DATA_DIR  # noqa: E402

CACHE_PATH = os.path.join(DATA_DIR, "sde.pickle")
CACHE_VERSION = 7
LANGS = ("en", "fr", "de", "ru")   # langues des noms d'objets conservées

ACTIVITY_ALIASES = {
    "manufacturing": "manufacturing", "1": "manufacturing",
    "reaction": "reaction", "reactions": "reaction", "11": "reaction",
    "invention": "invention", "8": "invention",
    "copying": "copying", "5": "copying",
    "research_material": "research_material", "4": "research_material",
    "research_time": "research_time", "3": "research_time",
}


def _name(v) -> str:
    if isinstance(v, dict):
        return v.get("en") or next(iter(v.values()), "") or ""
    return v or ""


def _names(v) -> dict:
    if isinstance(v, dict):
        out = {k: v[k] for k in LANGS if v.get(k)}
        out.setdefault("en", _name(v))
        return out
    return {"en": v or ""}


def _key(rec: dict, *alts):
    for k in ("_key",) + alts:
        if k in rec and rec[k] is not None:
            return rec[k]
    return None


@dataclass
class Activity:
    time: int = 0
    materials: list = field(default_factory=list)   # [(type_id, qty)]
    products: list = field(default_factory=list)    # [(type_id, qty, probability)]
    skills: list = field(default_factory=list)      # [(type_id, level)]


@dataclass
class Blueprint:
    bp_id: int
    max_runs: int
    activities: dict  # nom d'activité -> Activity


class SDE:
    def __init__(self):
        self.build: str | None = None
        self.lang = "en"
        self.types: dict[int, dict] = {}
        self.groups: dict[int, dict] = {}
        self.categories: dict[int, str] = {}
        self.blueprints: dict[int, Blueprint] = {}
        # produit -> (bp_id, activité, quantité par run)
        self.producer: dict[int, tuple[int, str, int]] = {}
        # bp T2 -> (bp T1, runs de base, probabilité de base)
        self.invented_from: dict[int, tuple[int, int, float]] = {}
        # dogma : compétences requises, slot des modules, rang/attributs des compétences
        self.req_skills: dict[int, list[tuple[int, int]]] = {}
        self.slot: dict[int, str] = {}
        self.skill_meta: dict[int, tuple[int, int, int]] = {}   # rang, attribut primaire, secondaire
        self._name_index: dict[str, int] | None = None
        # carte : systèmes de New Eden, régions, constellations, portes
        self.systems: dict[int, dict] = {}
        self.regions: dict[int, str] = {}
        self.constellations: dict[int, str] = {}
        self.gates: dict[int, set] = {}
        # planétaire : planètes par système, schémas de production (P0 -> P4)
        self.planets: dict[int, list[tuple[int, int]]] = {}       # système -> [(type de planète, index)]
        self.pi_schematics: dict[int, dict] = {}                   # schéma -> {cycle, out: (type, qté), in: [(type, qté)]}
        self.pi_producer: dict[int, int] = {}                      # produit PI -> schéma

    # ------------------------------------------------------------------ helpers
    def name(self, tid: int, lang: str | None = None) -> str:
        t = self.types.get(tid)
        if not t:
            return f"#{tid}"
        return t["names"].get(lang or self.lang) or t["name"]

    def name_en(self, tid: int) -> str:
        t = self.types.get(tid)
        return t["name"] if t else f"#{tid}"

    def group_name(self, tid: int) -> str:
        """Nom de groupe dans la langue choisie (affichage)."""
        t = self.types.get(tid)
        g = self.groups.get(t["group"]) if t else None
        return (g["names"].get(self.lang) or g["name"]) if g else ""

    def group_name_en(self, tid: int) -> str:
        t = self.types.get(tid)
        g = self.groups.get(t["group"]) if t else None
        return g["name"] if g else ""

    def category_name(self, tid: int) -> str:
        """Nom anglais de la catégorie (sert aux règles internes)."""
        t = self.types.get(tid)
        g = self.groups.get(t["group"]) if t else None
        return self.categories.get(g["category"], "") if g else ""

    def volume(self, tid: int) -> float:
        t = self.types.get(tid)
        return float(t.get("volume") or 0) if t else 0.0

    def is_t2(self, tid: int) -> bool:
        p = self.producer.get(tid)
        return bool(p and p[0] in self.invented_from)

    def search(self, q: str, limit: int = 25, buildable_only: bool = True):
        q = q.lower().strip()
        if not q:
            return []
        out = []
        for tid, t in self.types.items():
            if not t.get("published"):
                continue
            if buildable_only and tid not in self.producer:
                continue
            best = None
            for n in {t["name"].lower(), (t["names"].get(self.lang) or "").lower()}:
                if n and q in n:
                    sc = (0 if n.startswith(q) else 1, len(n))
                    best = sc if best is None or sc < best else best
            if best:
                out.append((best, tid))
        out.sort()
        res = []
        for _, tid in out[:limit]:
            item = {"type_id": tid, "name": self.name(tid)}
            if self.lang != "en" and self.name(tid) != self.name_en(tid):
                item["alt"] = self.name_en(tid)
            res.append(item)
        return res

    def find_type_by_name(self, name: str) -> int | None:
        nl = name.lower()
        for tid, t in self.types.items():
            if t["name"].lower() == nl:
                return tid
        return None

    def find_any(self, name: str) -> int | None:
        """Retrouve un objet par son nom exact dans n'importe quelle langue (import de fits, D-scan…)."""
        if self._name_index is None:
            idx = {}
            for tid, t in self.types.items():
                for n in t["names"].values():
                    key = n.lower().strip()
                    # priorité aux objets publiés en cas d'homonymes
                    if key and (key not in idx or (t.get("published") and not self.types[idx[key]].get("published"))):
                        idx[key] = tid
            self._name_index = idx
        return self._name_index.get(name.lower().strip())

    def __getstate__(self):
        d = dict(self.__dict__)
        d["_name_index"] = None   # reconstruit à la demande, inutile de le stocker
        return d

    # ------------------------------------------------------------------ parsing
    @classmethod
    def from_zip_bytes(cls, raw: bytes, build: str | None = None) -> "SDE":
        sde = cls()
        sde.build = build
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            members = {os.path.basename(n): n for n in zf.namelist()}

            def lines(fname):
                if fname not in members:
                    raise RuntimeError(f"Fichier {fname} absent du SDE (format CCP modifié ?)")
                with zf.open(members[fname]) as fh:
                    for line in io.TextIOWrapper(fh, encoding="utf-8"):
                        line = line.strip()
                        if line:
                            yield json.loads(line)

            for rec in lines("categories.jsonl"):
                sde.categories[int(_key(rec, "categoryID"))] = _name(rec.get("name"))
            for rec in lines("groups.jsonl"):
                sde.groups[int(_key(rec, "groupID"))] = {
                    "name": _name(rec.get("name")), "names": _names(rec.get("name")),
                    "category": int(rec.get("categoryID") or 0),
                }
            for rec in lines("types.jsonl"):
                tid = int(_key(rec, "typeID"))
                sde.types[tid] = {
                    "name": _name(rec.get("name")), "names": _names(rec.get("name")),
                    "group": int(rec.get("groupID") or 0),
                    "published": bool(rec.get("published", False)),
                    "volume": rec.get("volume") or 0,
                    "market_group": rec.get("marketGroupID"),
                    "meta_group": rec.get("metaGroupID"),
                    "portion": rec.get("portionSize") or 1,
                }
            for rec in lines("blueprints.jsonl"):
                bp_id = int(_key(rec, "blueprintTypeID"))
                acts = {}
                for aname, a in (rec.get("activities") or {}).items():
                    an = ACTIVITY_ALIASES.get(str(aname))
                    if not an:
                        continue
                    acts[an] = Activity(
                        time=int(a.get("time") or 0),
                        materials=[(int(m["typeID"]), int(m["quantity"])) for m in a.get("materials") or []],
                        products=[(int(p["typeID"]), int(p["quantity"]), float(p.get("probability") or 1.0))
                                  for p in a.get("products") or []],
                        skills=[(int(s["typeID"]), int(s["level"])) for s in a.get("skills") or []],
                    )
                sde.blueprints[bp_id] = Blueprint(bp_id, int(rec.get("maxProductionLimit") or 1), acts)
            if "mapSolarSystems.jsonl" in members:
                sde._load_map(lines, members)
            if "mapPlanets.jsonl" in members:
                for rec in lines("mapPlanets.jsonl"):
                    sid = int(rec.get("solarSystemID") or 0)
                    if sid in sde.systems and rec.get("typeID"):
                        sde.planets.setdefault(sid, []).append((int(rec["typeID"]), int(rec.get("celestialIndex") or 0)))
            if "planetSchematics.jsonl" in members:
                for rec in lines("planetSchematics.jsonl"):
                    ins, out = [], None
                    for t in rec.get("types") or []:
                        tid, q = int(_key(t, "typeID")), int(t.get("quantity") or 1)
                        if t.get("isInput"):
                            ins.append((tid, q))
                        else:
                            out = (tid, q)
                    if out:
                        sch = int(_key(rec, "schematicID"))
                        sde.pi_schematics[sch] = {"cycle": int(rec.get("cycleTime") or 3600), "out": out, "in": ins,
                                                  "name": _name(rec.get("name"))}
                        sde.pi_producer.setdefault(out[0], sch)
            if "typeDogma.jsonl" in members:
                for rec in lines("typeDogma.jsonl"):
                    sde._dogma(int(_key(rec, "typeID")), rec)
        sde._index()
        return sde

    def _load_map(self, lines, members):
        def pos(v, keys):
            if isinstance(v, dict):
                return [float(v.get(k) or 0) for k in keys]
            if isinstance(v, (list, tuple)):
                return [float(x) for x in v[:len(keys)]]
            return None
        if "mapRegions.jsonl" in members:
            for rec in lines("mapRegions.jsonl"):
                self.regions[int(_key(rec, "regionID"))] = _name(rec.get("name"))
        if "mapConstellations.jsonl" in members:
            for rec in lines("mapConstellations.jsonl"):
                self.constellations[int(_key(rec, "constellationID"))] = _name(rec.get("name"))
        for rec in lines("mapSolarSystems.jsonl"):
            sid = int(_key(rec, "solarSystemID"))
            if not (30_000_000 <= sid <= 30_999_999):     # New Eden uniquement (ni WH, ni abysses)
                continue
            p3 = pos(rec.get("position"), ("x", "y", "z")) or [0, 0, 0]
            p2 = pos(rec.get("position2D"), ("x", "y"))
            self.systems[sid] = {
                "name": _name(rec.get("name") or rec.get("solarSystemName")),
                "region": int(rec.get("regionID") or 0), "constellation": int(rec.get("constellationID") or 0),
                "sec": float(rec.get("securityStatus") if rec.get("securityStatus") is not None else rec.get("security") or 0),
                "x": p2[0] if p2 else p3[0], "y": p2[1] if p2 else p3[2], "schematic": bool(p2),
            }
        if "mapStargates.jsonl" in members:
            for rec in lines("mapStargates.jsonl"):
                a = int(rec.get("solarSystemID") or 0)
                dest = rec.get("destination") or {}
                b = int((dest.get("solarSystemID") if isinstance(dest, dict) else 0) or rec.get("destinationSolarSystemID") or 0)
                if a in self.systems and b in self.systems and a != b:
                    self.gates.setdefault(a, set()).add(b)
                    self.gates.setdefault(b, set()).add(a)

    def find_system(self, name: str) -> int | None:
        n = (name or "").strip().lower()
        if not n:
            return None
        for sid, s in self.systems.items():
            if s["name"].lower() == n:
                return sid
        return None

    # attributs dogma : compétence requise n -> niveau requis n
    REQ_ATTRS = ((182, 277), (183, 278), (184, 279), (1285, 1286), (1289, 1287), (1290, 1288))
    SLOT_EFFECTS = {11: "low", 13: "med", 12: "high", 2663: "rig", 3772: "subsystem", 6306: "service"}

    def _dogma(self, tid, rec):
        attrs = {}
        for a in rec.get("dogmaAttributes") or []:
            attrs[int(a["attributeID"])] = a.get("value")
        reqs = []
        for sk_attr, lvl_attr in self.REQ_ATTRS:
            sk, lvl = attrs.get(sk_attr), attrs.get(lvl_attr)
            if sk and lvl:
                reqs.append((int(sk), int(lvl)))
        if reqs:
            self.req_skills[tid] = reqs
        if 275 in attrs:   # rang d'entraînement : c'est une compétence
            self.skill_meta[tid] = (int(attrs[275] or 1), int(attrs.get(180) or 165), int(attrs.get(181) or 166))
        for e in rec.get("dogmaEffects") or []:
            sl = self.SLOT_EFFECTS.get(int(e["effectID"]))
            if sl:
                self.slot[tid] = sl

    def _index(self):
        for bp_id, bp in self.blueprints.items():
            bp_type = self.types.get(bp_id)
            if bp_type is not None and not bp_type.get("published"):
                continue
            for act in ("manufacturing", "reaction"):
                a = bp.activities.get(act)
                if not a or not a.products:
                    continue
                pid, qty, _ = a.products[0]
                prod = self.types.get(pid)
                if not prod or not prod.get("published"):
                    continue
                # Garde le blueprint "normal" si plusieurs produisent le même item
                if pid not in self.producer:
                    self.producer[pid] = (bp_id, act, qty)
            inv = bp.activities.get("invention")
            if inv:
                for pid, qty, prob in inv.products:
                    if pid not in self.invented_from:
                        self.invented_from[pid] = (bp_id, qty, prob)

    # ------------------------------------------------------------------ cache
    def save(self, path: str = CACHE_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump((CACHE_VERSION, self), fh)

    @staticmethod
    def load_cached(path: str = CACHE_PATH) -> "SDE | None":
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as fh:
                ver, sde = pickle.load(fh)
            return sde if ver == CACHE_VERSION else None
        except Exception:
            return None


async def latest_build_number(client: httpx.AsyncClient) -> str | None:
    """Lit latest.jsonl et renvoie le numéro de build courant du SDE."""
    try:
        r = await client.get(SDE_LATEST_URL, timeout=30)
        r.raise_for_status()
        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("_key") == "sde" and rec.get("buildNumber"):
                return str(rec["buildNumber"])
            if rec.get("buildNumber"):
                return str(rec["buildNumber"])
    except Exception:
        return None
    return None


async def download_sde(client: httpx.AsyncClient, progress=None) -> SDE:
    build = await latest_build_number(client)
    if progress:
        progress(f"Téléchargement du SDE (build {build or '?'})…")
    async with client.stream("GET", SDE_ZIP_URL, timeout=600, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        buf = bytearray()
        async for chunk in r.aiter_bytes(1 << 20):
            buf.extend(chunk)
            if progress and total:
                progress(f"Téléchargement du SDE : {len(buf) * 100 // total} %")
    if progress:
        progress("Analyse du SDE…")
    sde = SDE.from_zip_bytes(bytes(buf), build)
    sde.save()
    return sde
