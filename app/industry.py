"""Moteur industriel : formules EVE, choix de structure, arbitrage fabriquer/acheter, plan de production.

Formules (état du jeu depuis la refonte Industry 2014 + ajustements ultérieurs) :
- Quantité par job = max(runs, ceil(round(runs * base * multiplicateur, 2)))
  multiplicateur = (1 - ME_bp) * (1 - bonus_rôle_structure) * (1 - bonus_rig * multiplicateur_sécurité)
- Valeur estimée (EIV) = runs * Σ(base * prix_ajusté)
- Coût du job = EIV * indice_système * (1 - bonus_coût_structure) + EIV * taxe_structure + EIV * surtaxe_SCC
- Invention/copie : EIV = 2 % de l'EIV de fabrication du produit T1
- Probabilité invention = base * (1 + (science1 + science2)/30 + encryption/40) * (1 + modif_décrypteur)
Tous les pourcentages réglables sont dans settings.json : vérifie-les contre ton jeu.
"""
from __future__ import annotations

import math
from collections import defaultdict

INF = float("inf")

# (ME %, TE %, coût %) par type de structure et activité
STRUCTURE_ROLES = {
    "Station NPC": {"manufacturing": (0, 0, 0), "invention": (0, 0, 0), "copying": (0, 0, 0)},
    "Raitaru": {"manufacturing": (1, 15, 3), "invention": (0, 15, 3), "copying": (0, 15, 3)},
    "Azbel": {"manufacturing": (1, 20, 4), "invention": (0, 20, 4), "copying": (0, 20, 4)},
    "Sotiyo": {"manufacturing": (1, 30, 5), "invention": (0, 30, 5), "copying": (0, 30, 5)},
    "Astrahus / Fortizar / Keepstar": {"manufacturing": (0, 0, 0), "invention": (0, 0, 0), "copying": (0, 0, 0)},
    "Athanor": {"reaction": (0, 0, 0)},
    "Tatara": {"reaction": (0, 25, 0)},
}
SEC_MULT = {"high": 1.0, "low": 1.9, "null": 2.1, "wh": 2.1}

RIG_CATEGORIES = {
    "all": "Tout", "equipment": "Équipement (modules)", "ammunition": "Munitions & charges",
    "drones_fighters": "Drones & chasseurs",
    "basic_small_ship": "Petits vaisseaux T1", "basic_medium_ship": "Vaisseaux moyens T1",
    "basic_large_ship": "Grands vaisseaux T1", "advanced_small_ship": "Petits vaisseaux T2/T3",
    "advanced_medium_ship": "Vaisseaux moyens T2/T3", "advanced_large_ship": "Grands vaisseaux T2",
    "capital_ship": "Capitaux", "advanced_components": "Composants avancés (T2)",
    "capital_components": "Composants capitaux", "structures": "Structures & composants de structure",
    "reactions": "Réactions", "other": "Autre",
}

DECRYPTORS = {
    # nom : (modif probabilité %, runs, ME, TE)
    "Accelerant Decryptor": (20, 1, 2, 10),
    "Attainment Decryptor": (80, 4, -1, 4),
    "Augmentation Decryptor": (-40, 9, -2, 2),
    "Optimized Attainment Decryptor": (90, 2, 1, -2),
    "Optimized Augmentation Decryptor": (-10, 7, 2, 0),
    "Parity Decryptor": (50, 3, 1, -2),
    "Process Decryptor": (10, 0, 3, 6),
    "Symmetry Decryptor": (0, 2, 1, 8),
}

_CAPITAL = ("carrier", "dreadnought", "freighter", "titan", "supercarrier", "force auxiliary",
            "capital industrial", "jump freighter", "lancer")
_LARGE = ("battleship", "black ops", "marauder")
_MEDIUM = ("cruiser", "battlecruiser", "recon", "heavy", "command ship", "strategic", "mining barge",
           "exhumer", "industrial", "transport", "blockade", "logistics")


def rig_category(sde, tid: int, activity: str) -> str:
    if activity == "reaction":
        return "reactions"
    cat = sde.category_name(tid).lower()
    grp = sde.group_name_en(tid).lower()
    meta = (sde.types.get(tid) or {}).get("meta_group")
    advanced = meta in (2, 14) or sde.is_t2(tid)
    if cat == "ship":
        if any(k in grp for k in _CAPITAL):
            return "capital_ship"
        if any(k in grp for k in _LARGE):
            size = "large"
        elif any(k in grp for k in _MEDIUM) and "frigate" not in grp:
            size = "medium"
        else:
            size = "small"
        return f"{'advanced' if advanced else 'basic'}_{size}_ship"
    if cat == "module" or cat == "subsystem" or cat == "implant":
        return "equipment"
    if cat == "charge":
        return "ammunition"
    if cat in ("drone", "fighter"):
        return "drones_fighters"
    if cat in ("structure", "structure module", "deployable", "starbase", "orbitals", "sovereignty structures"):
        return "structures"
    if "capital" in grp and "component" in grp:
        return "capital_components"
    if "structure" in grp and "component" in grp:
        return "structures"
    if "component" in grp or grp == "construction components":
        return "advanced_components"
    return "other"


class PriceBook:
    def __init__(self, settings, prices=None, adjusted=None, indices=None):
        self.s = settings
        self.prices = prices or {}        # {tid: {"sell","buy",...}}
        self.adjusted = adjusted or {}    # {tid: {"adj","avg"}}
        self.indices = indices or {}      # {system_id: {activity: idx}}

    def buy(self, tid):
        """Prix unitaire pour acquérir l'item."""
        p = self.prices.get(tid) or {}
        mode = self.s.get("buy_price_mode", "sell")
        v = p.get(mode) or p.get("sell" if mode == "buy" else "buy") or 0
        if not v:
            v = (self.adjusted.get(tid) or {}).get("avg") or 0
        return v or None

    def sell(self, tid):
        """Prix unitaire net encaissé à la revente (taxes et frais déduits)."""
        p = self.prices.get(tid) or {}
        mode = self.s.get("sell_price_mode", "sell")
        v = p.get(mode) or 0
        if not v:
            return None
        fees = self.s.get("sales_tax_pct", 0) + (self.s.get("broker_fee_pct", 0) if mode == "sell" else 0)
        return v * (1 - fees / 100)

    def adj(self, tid):
        return (self.adjusted.get(tid) or {}).get("adj") or 0

    def index(self, system_id, activity):
        return (self.indices.get(int(system_id or 0)) or {}).get(activity, 0.0)


class Engine:
    def __init__(self, sde, settings, prices: PriceBook, owned_bps=None, skills=None):
        self.sde = sde
        self.s = settings
        self.p = prices
        self.owned_bps = owned_bps or {}   # {bp_type_id: {"me","te"}}
        self.skill_levels = skills or {}   # {skill_type_id: level}
        self._ucost = {}
        self._decision = {}
        self.decryptor_ids = {n: sde.find_type_by_name(n) for n in DECRYPTORS}

    # ------------------------------------------------------------------ structures
    def structures_for(self, activity):
        out = []
        for st in self.s.get("structures") or []:
            if not st.get("enabled", True):
                continue
            role = STRUCTURE_ROLES.get(st.get("kind"), {}).get(activity)
            if role is None:
                continue
            if activity not in (st.get("activities") or [activity]):
                continue
            out.append(st)
        if not out:
            # structure virtuelle sans bonus pour que les calculs restent possibles
            out.append({"id": "_default", "name": "Sans structure configurée", "kind": "Station NPC",
                        "system_id": 30000142, "security": "high", "tax_pct": 0.25, "rigs": [],
                        "activities": [activity], "virtual": True})
        return out

    def _bonuses(self, st, activity, rigcat):
        kind = st.get("kind")
        role = STRUCTURE_ROLES.get(kind, {}).get(activity, (0, 0, 0))
        if st.get("virtual"):
            role = (0, 0, 0)
        mult = SEC_MULT.get(st.get("security", "high"), 1.0)
        rig_me = rig_te = 0.0
        for r in st.get("rigs") or []:
            applies = r.get("applies", "all")
            if applies == "all" or applies == rigcat:
                rig_me += float(r.get("me") or 0)
                rig_te += float(r.get("te") or 0)
        return role, rig_me * mult, rig_te * mult

    # ------------------------------------------------------------------ blueprints
    def can_build(self, tid):
        prod = self.sde.producer.get(tid)
        if not prod:
            return False
        bp_id, act, _ = prod
        pol = self.s.get("build_policy") or {}
        if tid in set(pol.get("never_build") or []):
            return False
        if tid in set(pol.get("always_build") or []):
            return True
        if act == "reaction":
            return pol.get("build_reactions", True)
        if bp_id in self.sde.invented_from:
            return pol.get("invent_t2", True)
        bp_type = self.sde.types.get(bp_id) or {}
        if bp_type.get("market_group") or bp_id in self.owned_bps:
            return True
        return False   # BPC uniquement (faction, etc.) -> on achète

    def bp_me_te(self, bp_id, act, decryptor=None):
        if act == "reaction":
            return 0, 0
        if bp_id in self.sde.invented_from:
            d = DECRYPTORS.get(decryptor) if decryptor else None
            return 2 + (d[2] if d else 0), 4 + (d[3] if d else 0)
        ov = (self.s.get("bp_overrides") or {}).get(str(bp_id))
        if ov:
            return float(ov.get("me", 0)), float(ov.get("te", 0))
        if bp_id in self.owned_bps:
            o = self.owned_bps[bp_id]
            return float(o["me"]), float(o["te"])
        return float(self.s.get("default_bp_me", 10)), float(self.s.get("default_bp_te", 20))

    def skill(self, key):
        return int((self.s.get("skills") or {}).get(key, 0))

    def time_skill_mult(self, act):
        if act == "manufacturing":
            return (1 - 0.04 * self.skill("industry")) * (1 - 0.03 * self.skill("advanced_industry"))
        if act == "reaction":
            return 1 - 0.04 * self.skill("reactions")
        if act in ("invention", "copying"):
            return 1 - 0.03 * self.skill("advanced_industry")
        return 1.0

    # ------------------------------------------------------------------ calculs de base
    @staticmethod
    def job_quantity(base, runs, mult):
        return max(runs, math.ceil(round(runs * base * mult, 2)))

    def eiv(self, materials, runs):
        return runs * sum(q * self.p.adj(t) for t, q in materials)

    def job_cost(self, eiv, st, activity):
        role, _, _ = self._bonuses(st, activity, "other")
        idx = self.p.index(st.get("system_id"), activity)
        tax = float(st.get("tax_pct") or 0)
        scc = float(self.s.get("scc_surcharge_pct", 4.0))
        return eiv * idx * (1 - role[2] / 100) + eiv * (tax + scc) / 100

    def mat_mult(self, st, activity, rigcat, bp_me):
        role, rig_me, _ = self._bonuses(st, activity, rigcat)
        m = (1 - role[0] / 100) * (1 - rig_me / 100)
        if activity == "manufacturing":
            m *= (1 - bp_me / 100)
        return m

    def time_mult(self, st, activity, rigcat, bp_te):
        role, _, rig_te = self._bonuses(st, activity, rigcat)
        m = (1 - role[1] / 100) * (1 - rig_te / 100) * self.time_skill_mult(activity)
        if activity == "manufacturing":
            m *= (1 - bp_te / 100)
        return m

    def best_structure(self, tid, runs=10, decryptor=None):
        """Choisit la structure qui minimise matériaux + coût du job pour ce produit."""
        bp_id, act, _ = self.sde.producer[tid]
        a = self.sde.blueprints[bp_id].activities[act]
        me, te = self.bp_me_te(bp_id, act, decryptor)
        rc = rig_category(self.sde, tid, act)
        eiv = self.eiv(a.materials, runs)
        best = None
        for st in self.structures_for(act):
            mm = self.mat_mult(st, act, rc, me)
            cost = sum(self.job_quantity(q, runs, mm) * (self.p.buy(t) or self.p.adj(t)) for t, q in a.materials)
            cost += self.job_cost(eiv, st, act)
            tm = self.time_mult(st, act, rc, te)
            key = (cost, a.time * tm)
            if best is None or key < best[0]:
                best = (key, st, mm, tm)
        return best[1], best[2], best[3]

    # ------------------------------------------------------------------ invention
    def invention_info(self, tid, decryptor=None):
        """Données d'invention pour un produit T2 (par BPC inventé)."""
        bp_id, _, _ = self.sde.producer[tid]
        t1_bp, base_runs, base_prob = self.sde.invented_from[bp_id]
        inv = self.sde.blueprints[t1_bp].activities["invention"]
        enc, sci = 0, []
        for sk, _lvl in inv.skills:
            name = self.sde.name_en(sk)
            lvl = self.skill_levels.get(sk)
            if "Encryption Methods" in name:
                enc = lvl if lvl is not None else self.skill("encryption_default")
            else:
                sci.append(lvl if lvl is not None else self.skill("science_default"))
        sci_sum = sum(sci[:2])
        d = DECRYPTORS.get(decryptor) if decryptor else None
        prob = base_prob * (1 + sci_sum / 30 + enc / 40) * (1 + (d[0] if d else 0) / 100)
        prob = min(prob, 1.0)
        runs = max(1, base_runs + (d[1] if d else 0))
        mats = list(inv.materials)
        if d and self.decryptor_ids.get(decryptor):
            mats.append((self.decryptor_ids[decryptor], 1))
        # coût d'une tentative : matériaux + job d'invention + copie du BPC T1 (1 run)
        t1_bp_obj = self.sde.blueprints[t1_bp]
        t1_man = t1_bp_obj.activities.get("manufacturing")
        t1_eiv = self.eiv(t1_man.materials, 1) if t1_man else 0
        st_inv = self.structures_for("invention")[0]
        best_inv = min(self.structures_for("invention"), key=lambda s: self.job_cost(0.02 * t1_eiv, s, "invention"))
        st_inv = best_inv
        job = self.job_cost(0.02 * t1_eiv, st_inv, "invention")
        st_copy = min(self.structures_for("copying"), key=lambda s: self.job_cost(0.02 * t1_eiv, s, "copying"))
        copy = self.job_cost(0.02 * t1_eiv, st_copy, "copying")
        mat_cost = sum(q * (self.p.buy(t) or 0) for t, q in mats)
        attempt = mat_cost + job + copy
        inv_time = inv.time * self.time_mult(st_inv, "invention", "other", 0)
        return {
            "t1_bp": t1_bp, "probability": prob, "runs": runs, "materials": mats,
            "attempt_cost": attempt, "job_cost": job + copy, "structure": st_inv,
            "cost_per_run": attempt / prob / runs, "time_per_attempt": inv_time,
            "encryption": enc, "science": sci[:2],
        }

    # ------------------------------------------------------------------ coût unitaire optimal
    def unit_cost(self, tid, optimize=True, _stack=None):
        """Coût unitaire : min(acheter, fabriquer) si optimize, sinon fabrique tout ce qui est fabricable."""
        key = (tid, optimize)
        if key in self._ucost:
            return self._ucost[key]
        _stack = _stack or set()
        buy = self.p.buy(tid)
        buy_v = buy if buy else INF
        if tid in _stack or not self.can_build(tid):
            self._ucost[key] = buy_v
            self._decision[key] = "buy"
            return buy_v
        build = self.build_unit_cost(tid, optimize, _stack | {tid})
        if optimize:
            choice = "build" if build < buy_v else "buy"
        else:
            choice = "build" if build < INF else "buy"
        self._decision[key] = choice
        self._ucost[key] = build if choice == "build" else buy_v
        return self._ucost[key]

    def decision(self, tid, optimize=True):
        self.unit_cost(tid, optimize)
        return self._decision.get((tid, optimize), "buy")

    def build_unit_cost(self, tid, optimize=True, _stack=None, decryptor="__default__"):
        if decryptor == "__default__":
            decryptor = self.s.get("default_decryptor") or None
        bp_id, act, out_qty = self.sde.producer[tid]
        a = self.sde.blueprints[bp_id].activities[act]
        st, mm, _tm = self.best_structure(tid, decryptor=decryptor)
        total = 0.0
        for m, q in a.materials:
            c = self.unit_cost(m, optimize, _stack)
            if c == INF:
                return INF
            total += q * mm * c
        total += self.job_cost(self.eiv(a.materials, 1), st, act)
        if bp_id in self.sde.invented_from:
            total += self.invention_info(tid, decryptor)["cost_per_run"]
        return total / out_qty

    def time_per_unit(self, tid, decryptor=None):
        bp_id, act, out_qty = self.sde.producer[tid]
        a = self.sde.blueprints[bp_id].activities[act]
        st, _, tm = self.best_structure(tid, decryptor=decryptor)
        return a.time * tm / out_qty, st

    # ------------------------------------------------------------------ plan complet
    def plan(self, target, quantity=1, optimize=False, overrides=None, stock=None, decryptor="__default__",
             max_depth=None):
        """target : un type_id, ou une liste [(type_id, quantité), …] pour planifier plusieurs produits ensemble.
        max_depth : ne fabriquer que jusqu'au niveau N de l'arbre (0 = seulement le produit final), acheter au-delà."""
        if decryptor == "__default__":
            decryptor = self.s.get("default_decryptor") or None
        overrides = {int(k): v for k, v in (overrides or {}).items()}
        stock = defaultdict(int, {int(k): int(v) for k, v in (stock or {}).items()})
        stock_used = defaultdict(int)
        wanted = defaultdict(int)
        for t, q in (target if isinstance(target, (list, tuple)) else [(target, quantity)]):
            if int(q) > 0:
                wanted[int(t)] += int(q)
        if not wanted:
            raise ValueError("Aucun produit à planifier.")
        for t in wanted:
            if t not in self.sde.producer:
                raise ValueError(f"{self.sde.name(t)} n'a pas de blueprint de fabrication.")
        roots = set(wanted)
        target = next(iter(wanted))
        quantity = wanted[target]

        def decide(tid):
            if tid in roots:
                return "build"
            if max_depth is not None and depth.get(tid, 0) > int(max_depth) and overrides.get(tid) != "build":
                return "buy"
            if tid in overrides:
                return overrides[tid] if (overrides[tid] == "buy" or self.can_build(tid)) else "buy"
            if not self.can_build(tid):
                return "buy"
            if optimize:
                return self.decision(tid, True)
            pol = self.s.get("build_policy") or {}
            if not pol.get("build_components", True) and tid != target:
                act = self.sde.producer[tid][1]
                if act == "manufacturing" and not self.sde.is_t2(tid):
                    return "buy"
            return "build"

        # 1) graphe des nœuds fabriqués + profondeur maximale
        dec, depth, children = {}, {t: 0 for t in roots}, defaultdict(set)
        order = list(roots)
        i = 0
        while i < len(order):
            tid = order[i]
            i += 1
            dec[tid] = decide(tid)
            if dec[tid] != "build":
                continue
            bp_id, act, _ = self.sde.producer[tid]
            for m, _q in self.sde.blueprints[bp_id].activities[act].materials:
                children[tid].add(m)
                if m not in depth:
                    depth[m] = depth[tid] + 1
                    order.append(m)
        # profondeur = plus long chemin (relaxation, le graphe est un DAG)
        changed = True
        guard = 0
        while changed and guard < 50:
            changed, guard = False, guard + 1
            for p_, cs in list(children.items()):
                for c in cs:
                    if depth.get(c, 0) < depth[p_] + 1:
                        depth[c] = depth[p_] + 1
                        changed = True

        # 2) propagation de la demande, niveau par niveau
        demand = defaultdict(float)
        for t, q in wanted.items():
            demand[t] = q
        jobs, inventions = [], []
        node_info = {}
        edges = []
        build_nodes = sorted([t for t in dec if dec[t] == "build"], key=lambda t: depth[t])
        for tid in build_nodes:
            need = int(math.ceil(demand[tid]))
            if tid not in roots and stock[tid] > 0:
                take = min(stock[tid], need)
                stock[tid] -= take
                stock_used[tid] += take
                need -= take
            bp_id, act, out_qty = self.sde.producer[tid]
            bp = self.sde.blueprints[bp_id]
            a = bp.activities[act]
            runs = int(math.ceil(need / out_qty)) if need > 0 else 0
            node_info[tid] = {"needed": need, "runs": runs, "produced": runs * out_qty}
            if runs == 0:
                continue
            is_t2 = bp_id in self.sde.invented_from
            inv = self.invention_info(tid, decryptor) if is_t2 else None
            max_runs = inv["runs"] if is_t2 else max(1, bp.max_runs)
            st, mm, tm = self.best_structure(tid, runs=min(runs, max_runs), decryptor=decryptor)
            me, te = self.bp_me_te(bp_id, act, decryptor)
            left = runs
            while left > 0:
                r = min(left, max_runs)
                left -= r
                mats = {m: self.job_quantity(q, r, mm) for m, q in a.materials}
                for m, q in mats.items():
                    demand[m] += q
                jobs.append({
                    "type_id": tid, "name": self.sde.name(tid), "activity": act, "runs": r,
                    "output": r * out_qty, "depth": depth[tid], "structure": st.get("name"),
                    "structure_virtual": bool(st.get("virtual")),
                    "me": me, "te": te, "duration_s": a.time * tm * r,
                    "job_cost": self.job_cost(self.eiv(a.materials, r), st, act),
                    "materials": [{"type_id": m, "name": self.sde.name(m), "qty": q} for m, q in mats.items()],
                })
            for m, q in a.materials:
                edges.append({"from": tid, "to": m})
            if is_t2:
                bpcs = int(math.ceil(runs / inv["runs"]))
                attempts = int(math.ceil(bpcs / inv["probability"]))
                for m, q in inv["materials"]:
                    demand[m] += q * attempts
                    edges.append({"from": tid, "to": m, "invention": True})
                    depth.setdefault(m, depth[tid] + 1)
                    if m not in dec:
                        dec[m] = "buy"
                inventions.append({
                    "type_id": tid, "name": self.sde.name(tid), "t1_blueprint": self.sde.name(inv["t1_bp"]),
                    "t1_blueprint_id": inv["t1_bp"],
                    "bpcs_needed": bpcs, "attempts": attempts, "probability": inv["probability"],
                    "runs_per_bpc": inv["runs"], "decryptor": decryptor or "Aucun",
                    "structure": inv["structure"].get("name"), "job_cost_total": inv["job_cost"] * attempts,
                    "duration_s": inv["time_per_attempt"],
                    "materials": [{"type_id": m, "name": self.sde.name(m), "qty": q * attempts} for m, q in inv["materials"]],
                })

        # 3) liste d'achats
        buy = []
        for tid, qty in demand.items():
            if dec.get(tid) == "build":
                continue
            need = int(math.ceil(qty))
            take = min(stock[tid], need) if stock[tid] > 0 else 0
            stock[tid] -= take
            stock_used[tid] += take
            to_buy = need - take
            price = self.p.buy(tid) or 0
            buy.append({"type_id": tid, "name": self.sde.name(tid), "needed": need, "in_stock": take,
                        "to_buy": to_buy, "unit_price": price, "total": price * to_buy,
                        "volume_m3": self.sde.volume(tid) * to_buy, "group": self.sde.group_name(tid),
                        "depth": depth.get(tid, 1)})
        buy.sort(key=lambda x: (-x["total"], x["name"]))

        # 4) synthèse
        mat_cost = sum(b["total"] for b in buy)
        job_cost = sum(j["job_cost"] for j in jobs) + sum(v["job_cost_total"] for v in inventions)
        transport = sum(b["volume_m3"] for b in buy) * float(self.s.get("transport_isk_per_m3") or 0)
        out_qty = self.sde.producer[target][2]
        produced = node_info.get(target, {}).get("produced", quantity)
        targets = []
        for t, q in wanted.items():
            us = self.p.sell(t) or 0
            est = self.build_unit_cost(t, optimize, {t}, decryptor=decryptor)
            targets.append({"type_id": t, "name": self.sde.name(t), "quantity": q, "unit_sell_net": us,
                            "revenue_net": us * q, "unit_cost_estimate": est if est != INF else None,
                            "no_market_price": not us})
        unit_sell = self.p.sell(target) or 0
        revenue = sum(x["revenue_net"] for x in targets)
        total_cost = mat_cost + job_cost + transport
        total_qty = sum(wanted.values())
        # coût de la quantité demandée (le surplus éventuel est valorisé au prorata)
        by_level = defaultdict(float)
        for j in jobs:
            by_level[j["depth"]] = max(by_level[j["depth"]], j["duration_s"])
        nodes = []
        for tid in dec:
            info = node_info.get(tid, {})
            nodes.append({"type_id": tid, "name": self.sde.name(tid), "decision": dec[tid],
                          "can_build": self.can_build(tid) or tid in roots, "depth": depth.get(tid, 0),
                          "needed": info.get("needed", int(math.ceil(demand.get(tid, 0)))),
                          "runs": info.get("runs", 0), "in_stock": stock_used.get(tid, 0),
                          "unit_buy": self.p.buy(tid) or 0, "activity": (self.sde.producer.get(tid) or (0, "", 0))[1]})
        jobs.sort(key=lambda j: (-j["depth"], j["structure"] or "", j["name"]))
        return {
            "target": {"type_id": target, "name": self.sde.name(target), "quantity": quantity,
                       "produced": produced, "out_per_run": out_qty},
            "targets": targets,
            "summary": {
                "material_cost": mat_cost, "job_cost": job_cost, "transport_cost": transport,
                "total_cost": total_cost, "revenue_net": revenue, "profit": revenue - total_cost,
                "margin_pct": (revenue - total_cost) / revenue * 100 if revenue else None,
                "unit_cost": total_cost / quantity if len(wanted) == 1 else None, "unit_sell_net": unit_sell,
                "multi": len(wanted) > 1, "total_quantity": total_qty,
                "job_count": len(jobs), "purchase_count": len(buy),
                "serial_time_s": sum(j["duration_s"] for j in jobs),
                "critical_path_s": sum(by_level.values()),
                "volume_m3": sum(b["volume_m3"] for b in buy),
                "optimize": optimize, "decryptor": decryptor or "Aucun",
            },
            "jobs": jobs, "inventions": inventions, "buy": buy, "nodes": nodes, "edges": edges,
            "max_depth": max_depth, "full_depth": self._full_depth(list(roots)),
        }

    def _full_depth(self, roots):
        """Profondeur maximale de l'arbre si tout était fabriqué (pour proposer les niveaux)."""
        best, seen, stack = 0, {}, [(r, 0) for r in roots]
        while stack:
            t, d = stack.pop()
            if seen.get(t, -1) >= d or d > 15:
                continue
            seen[t] = d
            best = max(best, d)
            if self.can_build(t):
                bp_id, act, _ = self.sde.producer[t]
                for m, _q in self.sde.blueprints[bp_id].activities[act].materials:
                    stack.append((m, d + 1))
        return best

    # ------------------------------------------------------------------ comparaison décrypteurs
    def invention_table(self, tid):
        rows = []
        for dname in [None] + list(DECRYPTORS):
            dec_id = self.decryptor_ids.get(dname) if dname else None
            self._ucost.clear()
            self._decision.clear()
            info = self.invention_info(tid, dname)
            unit = self.build_unit_cost(tid, True, {tid}, decryptor=dname)
            sell = self.p.sell(tid) or 0
            t, _ = self.time_per_unit(tid, dname)
            bp_id = self.sde.producer[tid][0]
            me, te = self.bp_me_te(bp_id, "manufacturing", dname)
            rows.append({
                "decryptor": dname or "Aucun", "decryptor_type_id": dec_id,
                "decryptor_label": self.sde.name(dec_id) if dec_id else "Aucun",
                "probability": info["probability"], "runs": info["runs"],
                "me": me, "te": te, "invention_cost_per_unit": info["cost_per_run"] / self.sde.producer[tid][2],
                "unit_cost": unit, "unit_sell_net": sell, "profit_per_unit": sell - unit if sell else None,
                "profit_per_hour": (sell - unit) / (t / 3600) if sell and t else None,
                "attempt_cost": info["attempt_cost"],
            })
        rows.sort(key=lambda r: -(r["profit_per_unit"] or -1e30))
        base = self.invention_info(tid, None)
        return {"type_id": tid, "name": self.sde.name(tid), "t1_blueprint": self.sde.name(base["t1_bp"]),
                "t1_blueprint_id": base["t1_bp"],
                "encryption_level": base["encryption"], "science_levels": base["science"],
                "datacores": [{"type_id": m, "name": self.sde.name(m), "qty": q,
                               "unit_price": self.p.buy(m) or 0} for m, q in base["materials"]],
                "rows": rows}
