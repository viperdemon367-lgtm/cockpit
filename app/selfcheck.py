"""Vérification de bon fonctionnement en conditions réelles (réseau requis).

    python -m app.selfcheck

Contrôle : données CCP, API ESI, prix Fuzzwork, cohérence d'un calcul complet.
Code de sortie 0 = tout est OK. À lancer après chaque patch EVE ou si un résultat paraît bizarre.
"""
import asyncio
import sys

from .esi import EsiClient
from .industry import Engine, PriceBook
from .opportunities import all_inputs
from .sde import SDE, download_sde, latest_build_number
from .settings import HUBS, load_settings

OK, KO = "  OK  ", "ÉCHEC "
failures = []


def check(cond, label, detail=""):
    print(f"[{OK if cond else KO}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(label)
    return cond


async def main():
    s = load_settings()
    esi = EsiClient(lambda: s)
    print("== Données statiques CCP (SDE)")
    sde = SDE.load_cached()
    latest = await latest_build_number(esi.client)
    check(latest is not None, "latest.jsonl lisible", f"build {latest}")
    if sde is None or (latest and sde.build != latest):
        print("   téléchargement du SDE…")
        sde = await download_sde(esi.client, print)
    check(len(sde.producer) > 3000, "Blueprints indexés", f"{len(sde.producer)} produits fabricables")
    check(len(sde.invented_from) > 500, "Invention indexée", f"{len(sde.invented_from)} BPC T2")
    raven = sde.find_type_by_name("Raven")
    tritanium = sde.find_type_by_name("Tritanium")
    hammer = sde.find_type_by_name("Hammerhead II")
    check(raven and raven in sde.producer, "Raven fabricable")
    check(hammer and sde.is_t2(hammer), "Hammerhead II inventable")
    check(len(sde.req_skills) > 5000 and len(sde.slot) > 1000, "Compétences requises et slots (dogma)",
          f"{len(sde.req_skills)} objets, {len(sde.slot)} modules")
    vexor = sde.find_type_by_name("Vexor")
    check(vexor and sde.req_skills.get(vexor), "Compétences du Vexor connues")

    check(len(sde.systems) > 5000 and len(sde.gates) > 5000, "Carte de la galaxie", f"{len(sde.systems)} systèmes")
    from . import galaxy
    jita, amarr = sde.find_system("Jita"), sde.find_system("Amarr")
    path = galaxy.route(galaxy.build_graph(sde), sde, jita, amarr, "secure") if jita and amarr else None
    check(path and 8 <= len(path) - 1 <= 60, "Itinéraire Jita → Amarr (le plus sûr)", f"{len(path) - 1 if path else '?'} sauts")

    from .planetary import PI
    pi = PI(sde) if sde.pi_schematics else None
    check(pi is not None and len(sde.pi_schematics) > 60, "Schémas planétaires", f"{len(sde.pi_schematics)} schémas")
    check(sum(len(v) for v in sde.planets.values()) > 30000, "Planètes de New Eden", f"{sum(len(v) for v in sde.planets.values())} planètes")
    if pi:
        tiers = {pi.tier(t) for t in pi.products()}
        check(tiers == {1, 2, 3, 4} and len(pi.p0_ids) == 15, "Chaîne P0 → P4 et 15 ressources P0", f"niveaux {sorted(tiers)}, {len(pi.p0_ids)} P0")

    print("== API ESI")
    adj = await esi.adjusted_prices()
    check(len(adj) > 10000, "/markets/prices", f"{len(adj)} prix ajustés")
    idx = await esi.cost_indices()
    check(len(idx) > 1000, "/industry/systems", f"{len(idx)} systèmes")
    jita = await esi.resolve_system("Jita")
    check(jita and jita["system_id"] == 30000142, "Résolution de système (Jita)")

    print("== Prix de marché")
    p = await esi.market_prices(HUBS["jita"], [tritanium, raven])
    trit = (p.get(tritanium) or {}).get("sell", 0)
    check(1 <= trit <= 50, "Prix Tritanium Jita plausible", f"{trit} ISK")
    try:
        await esi._fuzzwork_prices(HUBS["jita"], [tritanium])
        check(True, "Fuzzwork disponible")
    except Exception as e:
        check(False, "Fuzzwork disponible (repli ESI utilisé)", str(e))
    hist = await esi.market_history(10000002, raven)
    check(hist["daily_volume"] > 0, "Historique de marché ESI", f"{hist['daily_volume']:.0f} Raven/jour")

    print("== zKillboard")
    import httpx as _h
    try:
        r = await esi.client.get("https://zkillboard.com/api/stats/corporationID/109299958/",
                                 headers={"User-Agent": s.get("user_agent") or "Cockpit", "Accept-Encoding": "gzip"}, timeout=20)
        check(r.status_code == 200 and "shipsDestroyed" in r.text, "API zKillboard", f"HTTP {r.status_code}")
    except _h.HTTPError as e:
        check(False, "API zKillboard", str(e))

    try:
        act = await esi.system_activity()
        check(len(act) > 500, "Activité des systèmes (kills/sauts)", f"{len(act)} systèmes")
    except Exception as e:
        check(False, "Activité des systèmes", str(e))
    try:
        from . import galaxy as _g
        wh = _g.parse_evescout(await esi.evescout())
        check(True, "EVE-Scout (Thera/Turnur)", f"{len(wh)} connexions")
    except Exception as e:
        check(False, "EVE-Scout (Thera/Turnur)", str(e))

    print("== Calcul complet")
    for name, tid in (("Raven", raven), ("Hammerhead II", hammer)):
        types = all_inputs(sde, [tid]) | {tid}
        prices = await esi.market_prices(HUBS["jita"], types)
        eng = Engine(sde, s, PriceBook(s, prices, adj, idx))
        plan = eng.plan(tid, 1, optimize=True)
        sell = (prices.get(tid) or {}).get("sell", 0)
        unit = plan["summary"]["unit_cost"]
        ratio = unit / sell if sell else 0
        check(plan["jobs"] and plan["buy"], f"Plan {name} généré", f"{len(plan['jobs'])} jobs, {len(plan['buy'])} achats")
        check(0.3 < ratio < 2.0, f"Coût {name} cohérent avec le marché", f"coût {unit:,.0f} vs Jita {sell:,.0f} (ratio {ratio:.2f})")
    esi.cache.flush()
    await esi.client.aclose()
    print()
    if failures:
        print(f"{len(failures)} contrôle(s) en échec : {', '.join(failures)}")
        print("Si c'est l'API CCP qui a changé : ouvre le projet avec Claude Code et donne-lui ce rapport (voir CLAUDE.md).")
        return 1
    print("Tout est fonctionnel.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
