"""Planétaire (PI) : ressources des planètes, chaîne P0 -> P4, meilleurs systèmes dans un rayon de sauts.

Les planètes de chaque système et les schémas de production viennent du SDE de CCP (mapPlanets, planetSchematics).
La liste des ressources brutes (P0) de chaque type de planète est une règle fixe du jeu.
"""
from __future__ import annotations

from collections import Counter

from . import galaxy

PLANET_P0 = {
    "Barren": ["Aqueous Liquids", "Base Metals", "Carbon Compounds", "Micro Organisms", "Noble Metals"],
    "Gas": ["Aqueous Liquids", "Base Metals", "Ionic Solutions", "Noble Gas", "Reactive Gas"],
    "Ice": ["Aqueous Liquids", "Heavy Metals", "Micro Organisms", "Noble Gas", "Planktic Colonies"],
    "Lava": ["Base Metals", "Felsic Magma", "Heavy Metals", "Non-CS Crystals", "Suspended Plasma"],
    "Oceanic": ["Aqueous Liquids", "Carbon Compounds", "Complex Organisms", "Micro Organisms", "Planktic Colonies"],
    "Plasma": ["Base Metals", "Heavy Metals", "Noble Metals", "Non-CS Crystals", "Suspended Plasma"],
    "Storm": ["Aqueous Liquids", "Base Metals", "Ionic Solutions", "Noble Gas", "Suspended Plasma"],
    "Temperate": ["Aqueous Liquids", "Autotrophs", "Carbon Compounds", "Complex Organisms", "Micro Organisms"],
}
PLANET_ORDER = ["Barren", "Gas", "Ice", "Lava", "Oceanic", "Plasma", "Storm", "Temperate"]
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
         "XVII", "XVIII", "XIX", "XX"]


def planet_kind(sde, type_id) -> str | None:
    """« Planet (Temperate) » -> « Temperate » (None pour les planètes fracturées, inutilisables en PI)."""
    name = sde.name_en(type_id)
    for k in PLANET_ORDER:
        if f"({k})" in name or name.endswith(k):
            return k
    return None


class PI:
    def __init__(self, sde):
        self.sde = sde
        self.p0_ids = {}
        for names in PLANET_P0.values():
            for n in names:
                tid = sde.find_type_by_name(n)
                if tid:
                    self.p0_ids[n] = tid
        self.p0_by_id = {v: k for k, v in self.p0_ids.items()}
        self.kind_type = {}           # « Temperate » -> type_id de la planète (pour l'icône)
        for sid, pls in sde.planets.items():
            for tid, _ in pls:
                k = planet_kind(sde, tid)
                if k and k not in self.kind_type:
                    self.kind_type[k] = tid
        self._tier = {}

    # --- chaîne de production
    def tier(self, tid, _depth=0) -> int:
        if tid in self._tier:
            return self._tier[tid]
        sch = self.sde.pi_producer.get(tid)
        if sch is None or _depth > 8:
            t = 0
        else:
            t = 1 + max((self.tier(i, _depth + 1) for i, _ in self.sde.pi_schematics[sch]["in"]), default=0)
        self._tier[tid] = t
        return t

    def products(self):
        return sorted(self.sde.pi_producer, key=lambda t: (self.tier(t), self.sde.name(t)))

    def p0_needed(self, tid, _seen=None) -> set:
        sch = self.sde.pi_producer.get(tid)
        if sch is None:
            return {tid}
        out = set()
        for i, _ in self.sde.pi_schematics[sch]["in"]:
            out |= self.p0_needed(i)
        return out

    def p0_planets(self, p0_tid) -> list[str]:
        name = self.p0_by_id.get(p0_tid) or self.sde.name_en(p0_tid)
        return [k for k in PLANET_ORDER if name in PLANET_P0[k]]

    def tree(self, tid, qty=1.0, _depth=0):
        """Arbre de production : quantité d'intrants pour `qty` unités du produit."""
        sch = self.sde.pi_producer.get(tid)
        node = {"type_id": tid, "name": self.sde.name(tid), "tier": self.tier(tid), "qty": round(qty, 2)}
        if sch is None or _depth > 8:
            node["planets"] = self.p0_planets(tid)
            return node
        s = self.sde.pi_schematics[sch]
        out_q = s["out"][1]
        node["cycle_s"] = s["cycle"]
        node["children"] = [self.tree(i, qty * q / out_q, _depth + 1) for i, q in s["in"]]
        return node

    # --- planètes d'un système / d'une zone
    def system_kinds(self, sid) -> Counter:
        return Counter(k for k in (planet_kind(self.sde, t) for t, _ in self.sde.planets.get(sid, [])) if k)

    def system_p0(self, sid) -> set:
        out = set()
        for k in self.system_kinds(sid):
            out |= {self.p0_ids[n] for n in PLANET_P0[k] if n in self.p0_ids}
        return out

    def system_planets(self, sid):
        s = self.sde.systems[sid]
        rows = []
        for t, idx in sorted(self.sde.planets.get(sid, []), key=lambda x: x[1]):
            k = planet_kind(self.sde, t)
            rows.append({"name": f"{s['name']} {ROMAN[idx] if idx < len(ROMAN) else idx}", "type_id": t, "kind": k,
                         "p0": [{"type_id": self.p0_ids.get(n), "name": self.sde.name(self.p0_ids[n]) if n in self.p0_ids else n}
                                for n in PLANET_P0.get(k, [])]})
        return rows

    def area(self, center, jumps, bridges=()):
        graph = galaxy.build_graph(self.sde, bridges)
        dist = galaxy.within_jumps(graph, center, jumps)
        return {sid: d for sid, d in dist.items() if sid in self.sde.systems}

    def analyze(self, center, jumps, prices=None, bridges=()):
        prices = prices or {}
        dist = self.area(center, jumps, bridges)
        kinds_total, p0_systems = Counter(), Counter()
        systems = []
        for sid, d in dist.items():
            kinds = self.system_kinds(sid)
            kinds_total.update(kinds)
            p0 = self.system_p0(sid)
            for x in p0:
                p0_systems[x] += 1
            if kinds:
                systems.append({"system_id": sid, "jumps": d, "kinds": dict(kinds), "planets": sum(kinds.values()),
                                "p0_count": len(p0)})
        available = set(p0_systems)
        prods = []
        for tid in self.products():
            need = self.p0_needed(tid)
            missing = need - available
            sch = self.sde.pi_schematics[self.sde.pi_producer[tid]]
            sell = (prices.get(tid) or {}).get("sell") or 0
            cost = sum(((prices.get(i) or {}).get("sell") or 0) * q for i, q in sch["in"])
            out_q = sch["out"][1]
            per_cycle = sell * out_q - cost if sell else None
            # meilleur système « usine » : un seul système qui fournit tous les P0
            solo = [s for s in systems if need <= self.system_p0(s["system_id"])]
            prods.append({"type_id": tid, "name": self.sde.name(tid), "tier": self.tier(tid),
                          "p0": [{"type_id": x, "name": self.sde.name(x), "ok": x in available} for x in sorted(need, key=self.sde.name)],
                          "feasible": not missing, "missing": len(missing), "sell": sell,
                          "margin_hour": per_cycle * 3600 / sch["cycle"] if per_cycle is not None else None,
                          "value_hour": sell * out_q * 3600 / sch["cycle"] if sell else None,
                          "solo_systems": len(solo)})
        systems.sort(key=lambda s: (-s["p0_count"], -s["planets"], s["jumps"]))
        return {"center": center, "jumps": jumps, "systems_in_range": len(dist), "systems": systems[:60],
                "planets": sum(kinds_total.values()), "kinds": {k: kinds_total.get(k, 0) for k in PLANET_ORDER},
                "kind_types": self.kind_type, "p0": [{"type_id": self.p0_ids[n], "name": self.sde.name(self.p0_ids[n]),
                                                       "systems": p0_systems.get(self.p0_ids[n], 0),
                                                       "planets": self.p0_planets(self.p0_ids[n])}
                                                      for n in sorted(self.p0_ids)],
                "products": prods}

    def best_systems(self, tid, center, jumps, bridges=(), limit=25):
        need = self.p0_needed(tid)
        dist = self.area(center, jumps, bridges)
        out = []
        for sid, d in dist.items():
            kinds = self.system_kinds(sid)
            if not kinds:
                continue
            have = self.system_p0(sid) & need
            # planètes utiles : celles qui fournissent au moins un P0 nécessaire
            useful = sum(n for k, n in kinds.items() if any(self.p0_ids.get(x) in need for x in PLANET_P0[k]))
            out.append({"system_id": sid, "name": self.sde.systems[sid]["name"], "jumps": d,
                        "sec": galaxy.display_sec(self.sde.systems[sid]["sec"]),
                        "region": self.sde.regions.get(self.sde.systems[sid]["region"], ""),
                        "coverage": len(have), "needed": len(need), "useful_planets": useful, "kinds": dict(kinds),
                        "missing": [self.sde.name(x) for x in sorted(need - have, key=self.sde.name)]})
        out.sort(key=lambda r: (-r["coverage"], -r["useful_planets"], r["jumps"]))
        return out[:limit]
