"""Recherche des meilleures opportunités d'ISK.

1. Industrie : pour chaque produit fabricable, coût optimal (acheter vs fabriquer chaque composant),
   prix de revente net, marge, ISK/heure de slot, puis filtrage par liquidité réelle (volume/jour ESI).
   Le score « ISK/jour réaliste » = min(capacité d'1 slot sur 24 h, 10 % du volume quotidien) × profit unitaire.
2. Arbitrage : écart de prix entre hubs (Jita, Amarr, Dodixie, Rens, Hek), transport et taxes inclus.
"""
from __future__ import annotations

from .industry import INF, Engine, PriceBook, rig_category


def candidate_products(sde, engine: Engine, scan: dict):
    out = []
    for tid, (bp_id, act, _qty) in sde.producer.items():
        t = sde.types.get(tid) or {}
        if not t.get("published") or not t.get("market_group"):
            continue
        if not engine.can_build(tid):
            continue
        if act == "reaction" and not scan.get("include_reactions", True):
            continue
        if bp_id in sde.invented_from and not scan.get("include_t2", True):
            continue
        rc = rig_category(sde, tid, act)
        if rc in ("capital_ship", "capital_components") and not scan.get("include_capitals", False):
            continue
        out.append(tid)
    return out


def all_inputs(sde, products):
    """Tous les items qui peuvent intervenir dans l'arbre de fabrication des produits."""
    seen = set()
    stack = list(products)
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        prod = sde.producer.get(t)
        if not prod:
            continue
        bp_id, act, _ = prod
        for m, _q in sde.blueprints[bp_id].activities[act].materials:
            stack.append(m)
        if bp_id in sde.invented_from:
            t1 = sde.invented_from[bp_id][0]
            for m, _q in sde.blueprints[t1].activities["invention"].materials:
                seen.add(m)
    from .industry import DECRYPTORS
    for n in DECRYPTORS:
        d = sde.find_type_by_name(n)
        if d:
            seen.add(d)
    return seen


def score_industry(sde, engine: Engine, products, scan):
    rows = []
    for tid in products:
        try:
            cost = engine.build_unit_cost(tid, optimize=True, _stack={tid})
        except Exception:
            continue
        if cost == INF or cost <= 0:
            continue
        sell = engine.p.sell(tid)
        if not sell:
            continue
        max_cost = float(scan.get("max_unit_cost") or 0)
        if max_cost and cost > max_cost:
            continue
        profit = sell - cost
        margin = profit / sell * 100
        t_unit, st = engine.time_per_unit(tid)
        bp_id, act, _ = sde.producer[tid]
        rows.append({
            "type_id": tid, "name": sde.name(tid), "group": sde.group_name(tid),
            "kind": "T2 (invention)" if bp_id in sde.invented_from else ("Réaction" if act == "reaction" else "T1"),
            "unit_cost": cost, "unit_sell_net": sell, "profit_per_unit": profit, "margin_pct": margin,
            "time_per_unit_s": t_unit, "profit_per_hour": profit / (t_unit / 3600) if t_unit else 0,
            "structure": st.get("name"),
            "sell_orders_volume": (engine.p.prices.get(tid) or {}).get("sell_vol", 0),
            "sell_raw": (engine.p.prices.get(tid) or {}).get(engine.s.get("sell_price_mode", "sell"), 0),
        })
    return rows


def finalize_industry(rows, histories, scan):
    out = []
    for r in rows:
        h = histories.get(r["type_id"])
        if h is None:
            continue
        r["daily_volume"] = h["daily_volume"]
        r["avg_price_7d"] = h["avg_price_7d"]
        if h["daily_volume"] < float(scan.get("min_daily_volume") or 0):
            continue
        slot_units_day = 86400 / r["time_per_unit_s"] if r["time_per_unit_s"] else 0
        market_units_day = h["daily_volume"] * 0.10   # on ne vise pas plus de 10 % du marché
        r["units_per_day_realistic"] = min(slot_units_day, market_units_day)
        r["isk_per_day_realistic"] = r["units_per_day_realistic"] * r["profit_per_unit"]
        # alerte si le prix actuel est loin de la moyenne 7 j (prix manipulé / pic temporaire)
        avg7 = h["avg_price_7d"]
        r["price_spike"] = bool(avg7 and r.get("sell_raw", 0) > avg7 * 1.25)
        out.append(r)
    out.sort(key=lambda r: -r["isk_per_day_realistic"])
    return out


def arbitrage(sde, settings, prices_by_hub: dict, hubs: dict, adjusted):
    a = settings.get("arbitrage") or {}
    tax = settings.get("sales_tax_pct", 0)
    broker = settings.get("broker_fee_pct", 0)
    per_m3 = float(settings.get("transport_isk_per_m3") or 0)
    instant = a.get("instant_sell", True)
    rows = []
    ids = set()
    for p in prices_by_hub.values():
        ids |= set(p)
    for tid in ids:
        vol = sde.volume(tid)
        for src, ps in prices_by_hub.items():
            buy_at = (ps.get(tid) or {}).get("sell") or 0
            avail = (ps.get(tid) or {}).get("sell_vol") or 0
            if not buy_at or not avail:
                continue
            for dst, pd in prices_by_hub.items():
                if dst == src:
                    continue
                d = pd.get(tid) or {}
                if instant:
                    sell_at = d.get("buy") or 0
                    net = sell_at * (1 - tax / 100)
                else:
                    sell_at = d.get("sell") or 0
                    net = sell_at * (1 - (tax + broker) / 100)
                if not sell_at:
                    continue
                unit_profit = net - buy_at - vol * per_m3
                if unit_profit <= 0:
                    continue
                margin = unit_profit / buy_at * 100
                if margin < float(a.get("min_margin_pct") or 0):
                    continue
                qty = avail if not instant else min(avail, d.get("buy_vol") or 0)
                rows.append({
                    "type_id": tid, "name": sde.name(tid), "from": hubs[src]["short"], "to": hubs[dst]["short"],
                    "from_id": src, "to_id": dst, "buy_price": buy_at, "sell_price": sell_at,
                    "unit_profit": unit_profit, "margin_pct": margin, "qty_available": qty,
                    "volume_m3_unit": vol, "potential_profit": unit_profit * qty,
                    "dst_region": hubs[dst]["region_id"],
                })
    rows = [r for r in rows if r["potential_profit"] >= float(a.get("min_profit") or 0)]
    rows.sort(key=lambda r: -r["potential_profit"])
    return rows
