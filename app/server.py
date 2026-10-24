"""Serveur local FastAPI : http://localhost:8765"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import traceback
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import alarm as alarmlib
from . import sounds as soundlib
from . import galaxy
from . import planetary
from . import doctrines as dstore
from . import fits as fitlib
from . import opportunities as opp
from . import pvp
from .esi import SCOPES, EsiClient, EsiError
from .industry import DECRYPTORS, RIG_CATEGORIES, STRUCTURE_ROLES, Engine, PriceBook
from .paths import DATA_DIR, STATIC_DIR
from .sde import SDE, download_sde, latest_build_number
from .settings import HUBS, all_markets, distribution, load_settings, save_settings
from .version import CHANGELOG, VERSION

ACCOUNT_PATH = os.path.join(DATA_DIR, "account.json")
ACTIVITIES = {1: "Fabrication", 3: "Recherche TE", 4: "Recherche ME", 5: "Copie", 8: "Invention",
              9: "Réaction", 11: "Réaction"}
FITTED = ("HiSlot", "MedSlot", "LoSlot", "RigSlot", "SubSystemSlot", "Implant", "Skill", "ServiceSlot")


def _load_account():
    try:
        with open(ACCOUNT_PATH, encoding="utf-8") as fh:
            a = json.load(fh)
        a["owned_bps"] = {int(k): v for k, v in a.get("owned_bps", {}).items()}
        a["char_skills"] = {int(c): {int(k): v for k, v in sk.items()} for c, sk in a.get("char_skills", {}).items()}
        a["loc_names"] = {int(k): v for k, v in a.get("loc_names", {}).items()}
        a["char_sp"] = {int(c): {int(k): v for k, v in sk.items()} for c, sk in a.get("char_sp", {}).items()}
        a["char_queue"] = {int(c): {int(k): tuple(v) for k, v in q.items()} for c, q in a.get("char_queue", {}).items()}
        a["char_attrs"] = {int(c): v for c, v in a.get("char_attrs", {}).items()}
        a["char_total_sp"] = {int(c): v for c, v in a.get("char_total_sp", {}).items()}
        a["standings"] = {k: {int(i): v for i, v in (a.get("standings") or {}).get(k, {}).items()}
                          for k in ("personal", "corp", "alliance")}
        return a
    except Exception:
        return {}


state = {
    "settings": load_settings(), "sde": SDE.load_cached(), "sde_status": "",
    "assets": {}, "assets_time": None, "owned_bps": {}, "char_skills": {}, "loc_names": {}, "divisions": {},
    "char_sp": {}, "char_queue": {}, "char_attrs": {}, "char_total_sp": {}, "update": None, "standings": {},
    "scan": {"running": False, "progress": "", "result": None, "error": None},
    "arb": {"running": False, "progress": "", "result": None, "error": None},
}
state.update(_load_account())
esi = EsiClient(lambda: state["settings"])


def _save_account():
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {k: state[k] for k in ("assets", "assets_time", "owned_bps", "char_skills", "loc_names", "divisions",
                                  "char_sp", "char_queue", "char_attrs", "char_total_sp", "standings")}
    tmp = ACCOUNT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, ACCOUNT_PATH)


def S():
    return state["settings"]


def _apply_lang():
    if state["sde"] is not None:
        state["sde"].lang = S().get("lang") or "en"


_apply_lang()


def need_sde():
    if state["sde"] is None:
        raise HTTPException(409, "Les données du jeu ne sont pas encore chargées. Patiente pendant le téléchargement "
                                 "(statut en bas à gauche) puis réessaie.")
    return state["sde"]


async def _sde_update(force=False):
    try:
        cur = state["sde"]
        if cur and not force:
            latest = await latest_build_number(esi.client)
            if not latest or latest == cur.build:
                state["sde_status"] = "À jour"
                return
        state["sde_status"] = "Téléchargement des données du jeu…"
        state["sde"] = await download_sde(esi.client, lambda m: state.__setitem__("sde_status", m))
        _apply_lang()
        state["sde_status"] = "À jour"
    except Exception as e:
        state["sde_status"] = f"Erreur : {e}. Vérifie ta connexion internet puis clique « Réessayer »."


def _vtuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


async def _check_update():
    """Si la corpo publie un manifeste (update_manifest_url), signale une version plus récente."""
    url = distribution().get("update_manifest_url")
    if not url:
        return
    try:
        r = await esi.client.get(url, timeout=15)
        j = r.json()
        if _vtuple(j.get("version")) > _vtuple(VERSION):
            state["update"] = j
    except Exception:
        pass


async def _refresh_corp_doctrines():
    url = distribution().get("doctrines_url")
    if not url:
        return False
    r = await esi.client.get(url, timeout=20)
    r.raise_for_status()
    dstore.save_corp_cache(r.json())
    return True


async def _startup_tasks():
    await asyncio.gather(_sde_update(), _check_update(), _safe(_refresh_corp_doctrines()), _safe(esi.refresh_affiliations()))


async def _safe(coro):
    try:
        return await coro
    except Exception:
        return None


@asynccontextmanager
async def lifespan(_app):
    asyncio.create_task(_startup_tasks())   # données du jeu, mise à jour dispo, doctrines corpo, affiliations
    yield


app = FastAPI(title="Cockpit", lifespan=lifespan)


@app.exception_handler(Exception)
async def all_errors(_req, exc):
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    traceback.print_exc()
    return JSONResponse({"detail": f"{type(exc).__name__} : {exc}"}, status_code=500)


# ---------------------------------------------------------------------- statut / SDE
@app.get("/api/status")
async def status():
    sde = state["sde"]
    dist = distribution()
    return {"sde_loaded": sde is not None, "sde_build": sde.build if sde else None,
            "sde_status": state["sde_status"], "characters": esi.characters(),
            "assets_time": state["assets_time"], "esi_configured": bool(S().get("esi_client_id")),
            "preconfigured": bool(dist.get("esi_client_id")), "corp_name": dist.get("corp_name") or S().get("corp_name"),
            "setup_done": bool(S().get("setup_done")), "scopes": SCOPES, "callback_url": S().get("callback_url"),
            "structures": len(S().get("structures") or []), "version": VERSION, "update": state["update"],
            "last_seen_version": S().get("last_seen_version")}


@app.get("/api/version")
async def version():
    return {"version": VERSION, "changelog": CHANGELOG, "update": state["update"]}


@app.post("/api/sde/update")
async def sde_update():
    asyncio.create_task(_sde_update(force=True))
    return {"ok": True}


# ---------------------------------------------------------------------- réglages
@app.get("/api/settings")
async def get_settings():
    return {"settings": S(), "hubs": HUBS, "structure_kinds": {k: list(v) for k, v in STRUCTURE_ROLES.items()},
            "rig_categories": RIG_CATEGORIES, "decryptors": list(DECRYPTORS)}


@app.post("/api/settings")
async def post_settings(req: Request):
    body = await req.json()
    for st in body.get("structures") or []:
        if st.get("system_name") and not st.get("system_id"):
            try:
                info = await esi.resolve_system(st["system_name"])
                if info:
                    st.update(system_id=info["system_id"], system_name=info["name"],
                              sec_status=info["security"], security=info["band"])
            except Exception:
                pass
    state["settings"] = {**S(), **body}
    save_settings(state["settings"])
    _apply_lang()
    return {"ok": True, "settings": state["settings"]}


@app.get("/api/system")
async def system(name: str):
    info = await esi.resolve_system(name)
    if not info:
        raise HTTPException(404, f"Système « {name} » introuvable. Vérifie l'orthographe (ex. 1DQ1-A, Jita).")
    idx = (await esi.cost_indices()).get(info["system_id"], {})
    return {**info, "cost_indices": idx}


@app.get("/api/search")
async def search(q: str, all: bool = False):
    return need_sde().search(q, buildable_only=not all)


# ---------------------------------------------------------------------- moteur
async def make_engine(type_ids, market_id=None):
    sde = need_sde()
    s = S()
    market = all_markets(s).get(market_id or s.get("price_market") or "jita") or HUBS["jita"]
    adjusted, indices = await asyncio.gather(esi.adjusted_prices(), esi.cost_indices())
    prices = await esi.market_prices(market, type_ids)
    esi.cache.flush()
    skills = {}
    for sk in state["char_skills"].values():
        for k, v in sk.items():
            skills[k] = max(skills.get(k, 0), v)
    return Engine(sde, s, PriceBook(s, prices, adjusted, indices), state["owned_bps"], skills)


def stock_from_sources(sources):
    """Stock utilisable : exclut modules montés, implants et vaisseaux assemblés."""
    sde = state["sde"]
    stock = defaultdict(int)
    if not sources or not state["assets"]:
        return stock
    chars = set(int(c) for c in sources.get("characters") or [])
    divs = set(sources.get("corp_divisions") or [])
    locs = set(int(x) for x in sources.get("location_ids") or [])
    for src, items in state["assets"].items():
        kind, owner = src.split(":")
        for it in items:
            flag = str(it.get("location_flag", ""))
            if flag.startswith(FITTED):
                continue
            if it.get("is_singleton") and sde and sde.category_name(it["type_id"]) == "Ship":
                continue
            if locs and it.get("root_location") not in locs:
                continue
            if kind == "char" and int(owner) in chars:
                stock[it["type_id"]] += it["quantity"]
            elif kind == "corp" and flag in divs:
                stock[it["type_id"]] += it["quantity"]
    return stock


@app.post("/api/plan")
async def plan(req: Request):
    b = await req.json()
    sde = need_sde()
    items = b.get("items") or [{"type_id": b.get("type_id"), "quantity": b.get("quantity", 1)}]
    targets = [(int(x["type_id"]), max(1, int(x.get("quantity") or 1))) for x in items if x.get("type_id")]
    if not targets:
        raise HTTPException(400, "Ajoute au moins un produit.")
    types = opp.all_inputs(sde, [t for t, _ in targets]) | {t for t, _ in targets}
    eng = await make_engine(types)
    stock = {}
    if b.get("use_stock"):
        if not state["assets"] and esi.characters():
            await assets_refresh()
        stock = stock_from_sources(b.get("stock_sources") or S().get("stock_sources"))
    dec = b.get("decryptor", "__default__")
    if dec == "":
        dec = None
    md = b.get("max_depth")
    res = eng.plan(targets, optimize=bool(b.get("optimize")), overrides=b.get("overrides"),
                   stock=stock, decryptor=dec, max_depth=None if md in (None, "", "all") else int(md))
    res["stock_loaded"] = bool(state["assets"])
    cmp_id = b.get("compare_market") or S().get("compare_market")
    if cmp_id and cmp_id != S().get("price_market"):
        m = all_markets(S()).get(cmp_id)
        if m:
            try:
                cp = await esi.market_prices(m, [x["type_id"] for x in res["buy"]])
                for x in res["buy"]:
                    c = cp.get(x["type_id"]) or {}
                    x["compare_price"] = c.get("sell") or 0
                    x["compare_stock"] = c.get("sell_vol") or 0
                res["compare_market"] = m.get("short") or m.get("name")
                res["transport_isk_per_m3"] = float(S().get("transport_isk_per_m3") or 0)
            except Exception as e:
                res["compare_error"] = str(e)
    m = all_markets(S()).get(S().get("price_market") or "jita") or HUBS["jita"]
    res["price_market"] = m.get("short") or m.get("name")
    return res


@app.get("/api/invention/{type_id}")
async def invention(type_id: int):
    sde = need_sde()
    if not sde.is_t2(type_id):
        raise HTTPException(400, f"{sde.name(type_id)} ne s'obtient pas par invention.")
    eng = await make_engine(opp.all_inputs(sde, [type_id]) | {type_id})
    return eng.invention_table(type_id)


@app.get("/api/t2search")
async def t2search(q: str):
    sde = need_sde()
    return [x for x in sde.search(q, limit=80) if sde.is_t2(x["type_id"])][:25]


# ---------------------------------------------------------------------- scan d'opportunités
async def _run_scan():
    st = state["scan"]
    try:
        sde = need_sde()
        s = S()
        scan = s.get("scan") or {}
        st["progress"] = "Préparation de la liste des produits…"
        probe = Engine(sde, s, PriceBook(s), state["owned_bps"])
        products = opp.candidate_products(sde, probe, scan)
        types = opp.all_inputs(sde, products)
        st["progress"] = f"Récupération des prix de {len(types)} objets…"
        eng = await make_engine(types)
        st["progress"] = f"Calcul du coût de {len(products)} produits…"
        rows = await asyncio.to_thread(opp.score_industry, sde, eng, products, scan)
        min_margin = float(scan.get("min_margin_pct") or 0)
        rows = [r for r in rows if r["margin_pct"] >= min_margin and r["profit_per_unit"] > 0]
        rows.sort(key=lambda r: -r["profit_per_hour"])
        top = rows[: int(scan.get("history_top_n") or 250)]
        market = all_markets(s).get(s.get("price_market") or "jita") or HUBS["jita"]
        region = market.get("region_id") or 10000002
        hist = await esi.histories(region, [r["type_id"] for r in top], lambda m: st.__setitem__("progress", m))
        st["result"] = {"rows": opp.finalize_industry(top, hist, scan), "time": time.time(),
                        "scanned": len(products), "market": market.get("short") or market.get("name")}
        st["progress"] = "Terminé"
    except Exception as e:
        traceback.print_exc()
        st["error"] = getattr(e, "detail", None) or f"{type(e).__name__} : {e}"
    finally:
        st["running"] = False


@app.post("/api/scan/start")
async def scan_start():
    st = state["scan"]
    if not st["running"]:
        st.update(running=True, error=None, progress="Démarrage…")
        asyncio.create_task(_run_scan())
    return {"ok": True}


@app.get("/api/scan/status")
async def scan_status():
    return state["scan"]


async def _run_arb():
    st = state["arb"]
    try:
        sde = need_sde()
        s = S()
        a = s.get("arbitrage") or {}
        hubs = {h: HUBS[h] for h in a.get("hubs") or [] if h in HUBS}
        if len(hubs) < 2:
            raise ValueError("Sélectionne au moins deux hubs.")
        st["progress"] = "Prix moyens de l'univers…"
        adjusted = await esi.adjusted_prices()
        min_avg = float(a.get("min_avg_price") or 0)
        types = [t for t, v in adjusted.items()
                 if v.get("avg", 0) >= min_avg and (sde.types.get(t) or {}).get("market_group")]
        prices = {}
        for h, m in hubs.items():
            st["progress"] = f"Prix à {m['short']} ({len(types)} objets)…"
            prices[h] = await esi.market_prices(m, types)
        rows = opp.arbitrage(sde, s, prices, hubs, adjusted)
        top = rows[: int(a.get("history_top_n") or 200)]
        per_m3 = float(s.get("transport_isk_per_m3") or 0)
        for i, r in enumerate(top):
            if i % 25 == 0:
                st["progress"] = f"Vérification des volumes : {i}/{len(top)}"
            info = await esi.type_info(r["type_id"])
            pv = info.get("packaged_volume") or r["volume_m3_unit"]
            r["unit_profit"] += (r["volume_m3_unit"] - pv) * per_m3
            r["volume_m3_unit"] = pv
            h = await esi.market_history(r["dst_region"], r["type_id"])
            r["dst_daily_volume"] = h["daily_volume"]
            # on ne compte que ce que la destination absorbe en ~3 jours
            r["potential_profit"] = r["unit_profit"] * min(r["qty_available"], h["daily_volume"] * 3)
        top = [r for r in top if r["unit_profit"] > 0 and r["potential_profit"] > 0]
        top.sort(key=lambda r: -r["potential_profit"])
        esi.cache.flush()
        st["result"] = {"rows": top, "time": time.time()}
        st["progress"] = "Terminé"
    except Exception as e:
        traceback.print_exc()
        st["error"] = getattr(e, "detail", None) or f"{type(e).__name__} : {e}"
    finally:
        st["running"] = False


@app.post("/api/arbitrage/start")
async def arb_start():
    st = state["arb"]
    if not st["running"]:
        st.update(running=True, error=None, progress="Démarrage…")
        asyncio.create_task(_run_arb())
    return {"ok": True}


@app.get("/api/arbitrage/status")
async def arb_status():
    return state["arb"]


# ---------------------------------------------------------------------- personnages / SSO
PAGE = """<!doctype html><meta charset="utf-8"><title>Cockpit</title>
<body style="font-family:system-ui;background:#121924;color:#dfe6ee;display:grid;place-items:center;height:100vh;margin:0">
<div style="max-width:520px;text-align:center"><h2>{title}</h2><p>{msg}</p><p><a style="color:#e2a542" href="/#personnages">Retour à l'outil</a></p></div>"""


@app.get("/login")
async def login():
    try:
        return RedirectResponse(esi.login_url())
    except Exception as e:
        return HTMLResponse(PAGE.format(title="Connexion impossible", msg=e), status_code=400)


@app.get("/callback")
async def callback(request: Request, code: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(PAGE.format(title="Connexion annulée", msg="Aucun personnage n'a été ajouté."))
    try:
        info = await esi.handle_callback(code, request.query_params.get("state", ""))
    except Exception as e:
        return HTMLResponse(PAGE.format(title="Échec de la connexion", msg=e), status_code=400)
    return RedirectResponse(f"/#personnages?ok={info['name']}")


@app.delete("/api/characters/{cid}")
async def del_char(cid: int):
    esi.remove_character(cid)
    state["assets"].pop(f"char:{cid}", None)
    state["char_skills"].pop(cid, None)
    _save_account()
    return {"ok": True}


def _with_root(items):
    by_id = {it["item_id"]: it for it in items}
    for it in items:
        loc, seen = it["location_id"], 0
        while loc in by_id and seen < 10:
            loc, seen = by_id[loc]["location_id"], seen + 1
        it["root_location"] = loc
        if it["location_id"] in by_id and not str(it.get("location_flag", "")).startswith("CorpSAG"):
            parent = by_id[it["location_id"]]
            if str(parent.get("location_flag", "")).startswith("CorpSAG"):
                it["location_flag"] = parent["location_flag"]
    # on ne garde que l'utile pour limiter la taille du cache
    return [{k: it.get(k) for k in ("type_id", "quantity", "location_flag", "is_singleton", "root_location")}
            for it in items]


def _asset_summary(errors=None):
    locs = defaultdict(int)
    for items in state["assets"].values():
        for it in items:
            locs[it["root_location"]] += 1
    return {"errors": errors or [], "divisions": state["divisions"], "blueprints": len(state["owned_bps"]),
            "assets_time": state["assets_time"],
            "locations": [{"location_id": k, "items": v, "name": state["loc_names"].get(k, f"Emplacement {k}")}
                          for k, v in sorted(locs.items(), key=lambda x: -x[1])][:40],
            "sources": {k: len(v) for k, v in state["assets"].items()}}


@app.get("/api/assets")
async def assets_get():
    return _asset_summary()


@app.post("/api/assets/refresh")
async def assets_refresh():
    need_sde()
    assets, divisions, owned, skills, errors = {}, {}, {}, {}, []
    contacts_all = []
    corp_done = set()
    for ch in esi.characters():
        cid = ch["character_id"]
        try:
            assets[f"char:{cid}"] = _with_root(await esi.char_assets(cid))
        except Exception as e:
            errors.append(f"{ch['name']} — objets personnels : {e}")
        corp = ch.get("corporation_id")
        if corp and corp not in corp_done:
            try:
                assets[f"corp:{corp}"] = _with_root(await esi.corp_assets(cid))
                divisions[str(corp)] = await esi.corp_divisions(cid)
                corp_done.add(corp)
            except Exception:
                pass   # normal si le perso n'est pas Director : on essaie avec le suivant
        try:
            for bp in await esi.char_blueprints(cid):
                cur = owned.get(bp["type_id"])
                if not cur or bp["material_efficiency"] > cur["me"]:
                    owned[bp["type_id"]] = {"me": bp["material_efficiency"], "te": bp["time_efficiency"]}
        except Exception as e:
            errors.append(f"{ch['name']} — blueprints : {e}")
        try:
            sk = await esi.char_skills(cid)
            skills[cid] = sk["levels"]
            state["char_sp"][cid] = sk["sp"]
            state["char_total_sp"][cid] = sk["total_sp"]
            state["char_attrs"][cid] = await esi.char_attributes(cid)
        except Exception as e:
            errors.append(f"{ch['name']} — compétences : {e}")
        try:
            state["char_queue"][cid] = await esi.char_skillqueue(cid)
        except Exception:
            pass   # permission ajoutée en 1.2 : absente sur les persos connectés avant
        try:
            contacts_all.append(await esi.contacts(cid))
        except Exception:
            pass
    if esi.characters() and not corp_done:
        errors.append("Hangars de corporation non lus : il faut un personnage avec le rôle Director "
                      "(c'est normal si tu ne l'es pas, ton stock perso reste utilisé).")
    state.update(assets=assets, owned_bps=owned, char_skills=skills, assets_time=time.time(), divisions=divisions,
                 standings=pvp.merge_standings(contacts_all) if contacts_all else state["standings"])
    roots = {it["root_location"] for items in assets.values() for it in items}
    try:
        state["loc_names"] = await esi.location_names(roots, state["loc_names"])
    except Exception as e:
        errors.append(f"Noms d'emplacements : {e}")
    _save_account()
    return _asset_summary(errors)


@app.get("/api/jobs")
async def jobs():
    sde = need_sde()
    out, errors, facilities = [], [], set()
    now = datetime.now(timezone.utc)
    for ch in esi.characters():
        try:
            for j in await esi.char_jobs(ch["character_id"]):
                end = datetime.fromisoformat(j["end_date"].replace("Z", "+00:00"))
                pid = j.get("product_type_id") or j["blueprint_type_id"]
                facilities.add(j.get("station_id") or j.get("facility_id"))
                out.append({"character": ch["name"], "character_id": ch["character_id"],
                            "activity": ACTIVITIES.get(j["activity_id"], str(j["activity_id"])),
                            "type_id": pid, "name": sde.name(pid), "runs": j["runs"],
                            "status": j["status"], "end": j["end_date"],
                            "remaining_s": max(0, (end - now).total_seconds()),
                            "facility": j.get("station_id") or j.get("facility_id")})
        except Exception as e:
            errors.append(f"{ch['name']} : {e}")
    try:
        state["loc_names"] = await esi.location_names(facilities, state["loc_names"])
    except Exception:
        pass
    for j in out:
        j["facility_name"] = state["loc_names"].get(j["facility"], f"{j['facility']}")
    out.sort(key=lambda j: j["remaining_s"])
    return {"jobs": out, "errors": errors}


# ---------------------------------------------------------------------- personnages (détail)
@app.get("/api/login_url")
async def login_url():
    """Lien de connexion à ouvrir dans une fenêtre privée (pour ajouter un perso d'un autre compte EVE)."""
    try:
        return {"url": esi.login_url()}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/characters")
async def characters():
    out = []
    for c in esi.characters():
        cid = c["character_id"]
        c["total_sp"] = state["char_total_sp"].get(cid)
        c["skills_loaded"] = cid in state["char_skills"]
        out.append(c)
    return out


# ---------------------------------------------------------------------- PvP : doctrines et fits
def _pilots():
    """Données de compétences de chaque perso connecté, pour vérifier les fits."""
    out = []
    for c in esi.characters():
        cid = c["character_id"]
        out.append({"character_id": cid, "name": c["name"], "loaded": cid in state["char_skills"],
                    "levels": state["char_skills"].get(cid, {}), "sp": state["char_sp"].get(cid, {}),
                    "attrs": state["char_attrs"].get(cid, {}), "queue": state["char_queue"].get(cid, {})})
    return out


def _find_doc(did):
    for d in dstore.all_doctrines():
        if str(d["id"]) == str(did):
            return d
    raise HTTPException(404, "Doctrine introuvable.")


def _editable(did):
    d = _find_doc(did)
    if d["official"]:
        raise HTTPException(403, "Doctrine officielle de la corpo : duplique-la pour la modifier.")
    docs = dstore.load_user()
    return docs, next(x for x in docs if str(x["id"]) == str(did))


def _find_fit(fid):
    for d in dstore.all_doctrines():
        for f in d["fits"]:
            if str(f["id"]) == str(fid):
                return d, f
    raise HTTPException(404, "Fit introuvable.")


def _fit_summary(f, sde, pilots, need_cache=None):
    need = fitlib.requirements(fitlib.fit_type_ids(f), sde)
    checks = []
    for p in pilots:
        if not p["loaded"]:
            checks.append({"character_id": p["character_id"], "name": p["name"], "unknown": True})
            continue
        r = fitlib.check_pilot(need, p, sde)
        checks.append({"character_id": p["character_id"], "name": p["name"], "can_fly": r["can_fly"],
                       "missing_count": len(r["missing"]), "train_time_s": r["train_time_s"],
                       "only_queued": r["only_queued"]})
    return {"id": f["id"], "name": f["name"], "role": f.get("role", "DPS"), "notes": f.get("notes", ""),
            "ship_type_id": f["ship_type_id"], "ship_name": sde.name(f["ship_type_id"]),
            "ship_group": sde.group_name(f["ship_type_id"]), "module_count": sum(i["qty"] for i in f["items"]
                                                                                    if i["slot"] in fitlib.ESI_FLAG),
            "pilots": checks, "skills_known": bool(sde.req_skills)}


@app.get("/api/doctrines")
async def doctrines_list():
    sde = need_sde()
    pilots = _pilots()
    out = []
    for d in dstore.all_doctrines():
        out.append({"id": d["id"], "name": d["name"], "description": d.get("description", ""), "official": d["official"],
                    "fits": [_fit_summary(f, sde, pilots) for f in d["fits"]]})
    dist = distribution()
    return {"doctrines": out, "roles": dstore.ROLES, "corp_url": bool(dist.get("doctrines_url")),
            "corp_fetched": dstore.corp_cache_time()}


@app.post("/api/doctrines")
async def doctrine_save(req: Request):
    b = await req.json()
    docs = dstore.load_user()
    if b.get("id"):
        d = next((x for x in docs if str(x["id"]) == str(b["id"])), None)
        if d is None:
            raise HTTPException(403, "Doctrine officielle ou introuvable : duplique-la pour la modifier.")
        d["name"], d["description"] = b.get("name") or d["name"], b.get("description", d.get("description", ""))
    else:
        if not (b.get("name") or "").strip():
            raise HTTPException(400, "Donne un nom à la doctrine.")
        d = {"id": os.urandom(5).hex(), "name": b["name"].strip(), "description": b.get("description", ""), "fits": []}
        docs.append(d)
    dstore.save_user(docs)
    return {"id": d["id"]}


@app.delete("/api/doctrines/{did}")
async def doctrine_delete(did: str):
    docs, d = _editable(did)
    docs.remove(d)
    dstore.save_user(docs)
    return {"ok": True}


@app.post("/api/doctrines/{did}/duplicate")
async def doctrine_duplicate(did: str):
    src = _find_doc(did)
    docs = dstore.load_user()
    copy = json.loads(json.dumps(src))
    copy.update(id=os.urandom(5).hex(), name=src["name"] + " (copie)", official=False)
    for f in copy["fits"]:
        f["id"] = os.urandom(5).hex()
    docs.append(copy)
    dstore.save_user(docs)
    return {"id": copy["id"]}


@app.post("/api/doctrines/{did}/fits")
async def fits_add(did: str, req: Request):
    sde = need_sde()
    b = await req.json()
    docs, d = _editable(did)
    parsed = fitlib.parse_eft(b.get("eft", ""), sde)
    if not parsed:
        raise HTTPException(400, "Aucun fit reconnu. Colle un fit au format EFT : il commence par une ligne "
                                 "[Vaisseau, Nom du fit]. En jeu : fenêtre Fitting → Copier dans le presse-papiers.")
    added, warnings = [], []
    for p in parsed:
        if not p["ship_type_id"]:
            warnings.extend(p["unknown"])
            continue
        f = fitlib.new_fit(p, role=b.get("role") or "DPS", notes=b.get("notes", ""))
        d["fits"].append(f)
        added.append(f["name"])
        warnings.extend(f"{p['name']} : ligne non reconnue « {u} »" for u in p["unknown"])
    dstore.save_user(docs)
    return {"added": added, "warnings": warnings}


@app.get("/api/characters/{cid}/fittings")
async def char_fittings(cid: int):
    sde = need_sde()
    try:
        fl = await esi.char_fittings(cid)
    except EsiError as e:
        raise HTTPException(400, str(e))
    return [{"fitting_id": f["fitting_id"], "name": f["name"], "ship_type_id": f["ship_type_id"],
             "ship_name": sde.name(f["ship_type_id"]), "items": len(f.get("items") or [])}
            for f in sorted(fl, key=lambda f: (sde.name(f["ship_type_id"]), f["name"]))]


@app.post("/api/doctrines/{did}/fits_esi")
async def fits_from_game(did: str, req: Request):
    sde = need_sde()
    b = await req.json()
    docs, d = _editable(did)
    wanted = {int(x) for x in b.get("fitting_ids") or []}
    fl = await esi.char_fittings(int(b["character_id"]))
    added = []
    for f in fl:
        if f["fitting_id"] in wanted:
            nf = fitlib.new_fit(fitlib.from_esi_fitting(f, sde), role=b.get("role") or "DPS")
            d["fits"].append(nf)
            added.append(nf["name"])
    dstore.save_user(docs)
    return {"added": added}


@app.put("/api/fits/{fid}")
async def fit_update(fid: str, req: Request):
    b = await req.json()
    d, _ = _find_fit(fid)
    docs, dd = _editable(d["id"])
    f = next(x for x in dd["fits"] if str(x["id"]) == str(fid))
    for k in ("name", "role", "notes"):
        if k in b:
            f[k] = b[k]
    if b.get("eft"):
        parsed = fitlib.parse_eft(b["eft"], need_sde())
        if parsed and parsed[0]["ship_type_id"]:
            f["ship_type_id"], f["items"] = parsed[0]["ship_type_id"], parsed[0]["items"]
    if b.get("move_to"):
        target = next((x for x in docs if str(x["id"]) == str(b["move_to"])), None)
        if target and target is not dd:
            dd["fits"].remove(f)
            target["fits"].append(f)
    dstore.save_user(docs)
    return {"ok": True}


@app.delete("/api/fits/{fid}")
async def fit_delete(fid: str):
    d, _ = _find_fit(fid)
    docs, dd = _editable(d["id"])
    dd["fits"] = [x for x in dd["fits"] if str(x["id"]) != str(fid)]
    dstore.save_user(docs)
    return {"ok": True}


async def _prices_for(type_ids):
    s = S()
    markets = all_markets(s)
    main = markets.get(s.get("price_market") or "jita") or HUBS["jita"]
    prices = await esi.market_prices(main, type_ids)
    cmp_id = s.get("compare_market")
    cmp, cmp_m = {}, None
    if cmp_id and cmp_id != s.get("price_market") and markets.get(cmp_id):
        cmp_m = markets[cmp_id]
        try:
            cmp = await esi.market_prices(cmp_m, type_ids)
        except Exception:
            cmp, cmp_m = {}, None
    esi.cache.flush()
    return main, prices, cmp_m, cmp


@app.get("/api/fits/{fid}")
async def fit_detail(fid: str):
    sde = need_sde()
    d, f = _find_fit(fid)
    ids = [f["ship_type_id"]] + [i["type_id"] for i in f["items"]]
    main, prices, cmp_m, cmp = await _prices_for(ids)
    rows, total, total_cmp = [], 0.0, 0.0
    for tid, qty, slot in [(f["ship_type_id"], 1, "hull")] + [(i["type_id"], i["qty"], i["slot"]) for i in f["items"]]:
        p = (prices.get(tid) or {}).get("sell") or 0
        c = (cmp.get(tid) or {}).get("sell") or 0
        total += p * qty
        total_cmp += c * qty
        rows.append({"type_id": tid, "name": sde.name(tid), "qty": qty, "slot": slot,
                     "slot_label": "Coque" if slot == "hull" else fitlib.SLOT_LABELS.get(slot, slot),
                     "unit_price": p, "compare_price": c or None})
    need = fitlib.requirements(fitlib.fit_type_ids(f), sde)
    pilots = []
    for p in _pilots():
        if not p["loaded"]:
            pilots.append({"character_id": p["character_id"], "name": p["name"], "unknown": True})
            continue
        r = fitlib.check_pilot(need, p, sde)
        r.update(character_id=p["character_id"], name=p["name"], plan=fitlib.skill_plan_text(r["missing"], sde))
        pilots.append(r)
    lang = S().get("lang") or "en"
    return {"id": f["id"], "doctrine_id": d["id"], "doctrine": d["name"], "official": d["official"],
            "name": f["name"], "role": f.get("role"), "notes": f.get("notes", ""),
            "ship_type_id": f["ship_type_id"], "ship_name": sde.name(f["ship_type_id"]),
            "ship_group": sde.group_name(f["ship_type_id"]), "items": rows,
            "total": total, "total_compare": total_cmp if cmp_m else None,
            "market": main.get("short") or main.get("name"), "compare_market": (cmp_m or {}).get("short") or (cmp_m or {}).get("name"),
            "eft": fitlib.to_eft(f, sde, "en"), "eft_local": fitlib.to_eft(f, sde, lang),
            "multibuy": "\n".join(f"{sde.name(r['type_id'])}\t{r['qty']}" for r in rows),
            "skills_required": len(need), "skills_known": bool(sde.req_skills), "pilots": pilots}


@app.post("/api/fits/{fid}/push")
async def fit_push(fid: str, req: Request):
    sde = need_sde()
    b = await req.json()
    d, f = _find_fit(fid)
    payload = fitlib.to_esi_fitting(f, sde, description=f"{d['name']} — {f.get('role', '')}. {f.get('notes', '')}")
    try:
        await esi.push_fitting(int(b["character_id"]), payload)
    except EsiError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/doctrines/{did}/push_all")
async def doctrine_push_all(did: str, req: Request):
    sde = need_sde()
    b = await req.json()
    d = _find_doc(did)
    done, errors = 0, []
    for f in d["fits"]:
        try:
            await esi.push_fitting(int(b["character_id"]), fitlib.to_esi_fitting(f, sde, f"{d['name']} — {f.get('role', '')}"))
            done += 1
        except EsiError as e:
            errors.append(f"{f['name']} : {e}")
            if "Permission" in str(e):
                break
    return {"pushed": done, "errors": errors}


@app.post("/api/doctrines/{did}/order")
async def doctrine_order(did: str, req: Request):
    """Commande de flotte : total à acheter pour N exemplaires de chaque fit."""
    sde = need_sde()
    b = await req.json()
    d = _find_doc(did)
    qty_by_fit = {str(k): max(0, int(v or 0)) for k, v in (b.get("quantities") or {}).items()}
    need = defaultdict(int)
    for f in d["fits"]:
        n = qty_by_fit.get(str(f["id"]), 0)
        if not n:
            continue
        need[f["ship_type_id"]] += n
        for it in f["items"]:
            need[it["type_id"]] += it["qty"] * n
    if not need:
        raise HTTPException(400, "Indique au moins un exemplaire d'un fit.")
    stock = stock_from_sources(S().get("stock_sources")) if b.get("use_stock") else {}
    main, prices, cmp_m, cmp = await _prices_for(list(need))
    probe = Engine(sde, S(), PriceBook(S()), state["owned_bps"])
    rows, total, total_cmp = [], 0.0, 0.0
    for tid, q in need.items():
        have = min(int(stock.get(tid, 0)), q)
        buy = q - have
        p = (prices.get(tid) or {}).get("sell") or 0
        c = (cmp.get(tid) or {}).get("sell") or 0
        total += p * buy
        total_cmp += (c or p) * buy
        rows.append({"type_id": tid, "name": sde.name(tid), "needed": q, "in_stock": have, "to_buy": buy,
                     "unit_price": p, "compare_price": c or None, "total": p * buy,
                     "buildable": probe.can_build(tid), "is_hull": sde.category_name(tid) == "Ship"})
    rows.sort(key=lambda r: (not r["is_hull"], -r["total"]))
    return {"rows": rows, "total": total, "total_best": sum(min(r["unit_price"] or 1e18, r["compare_price"] or 1e18) * r["to_buy"]
                                                            for r in rows if r["unit_price"] or r["compare_price"]),
            "market": main.get("short") or main.get("name"), "compare_market": (cmp_m or {}).get("short"),
            "multibuy": "\n".join(f"{r['name']}\t{r['to_buy']}" for r in rows if r["to_buy"] > 0),
            "stock_loaded": bool(state["assets"])}


@app.get("/api/doctrines/{did}/report")
async def doctrine_report(did: str):
    sde = need_sde()
    d = _find_doc(did)
    pilots = [p for p in _pilots() if p["loaded"]]
    lines = [f"**Doctrine {d['name']}** — rapport du {datetime.now().strftime('%d/%m/%Y')}"]
    for p in pilots:
        ok, ko = [], []
        for f in d["fits"]:
            r = fitlib.check_pilot(fitlib.requirements(fitlib.fit_type_ids(f), sde), p, sde)
            label = f"{f['name']} ({sde.name(f['ship_type_id'])})"
            if r["can_fly"]:
                ok.append(label)
            else:
                ko.append(f"{label} — {len(r['missing'])} compétence(s), {_fmt_dur(r['train_time_s'])}"
                          + (" (en file)" if r["only_queued"] else ""))
        lines.append(f"\n__{p['name']}__")
        lines.append("✅ " + (", ".join(ok) if ok else "aucun fit"))
        for k in ko:
            lines.append("❌ " + k)
    if not pilots:
        lines.append("Aucun personnage avec compétences chargées : Personnages & stock → Rafraîchir depuis le jeu.")
    return {"text": "\n".join(lines)}


def _fmt_dur(s):
    s = int(s)
    d, h = s // 86400, (s % 86400) // 3600
    return f"{d} j {h} h" if d else f"{h} h {(s % 3600) // 60} min"


@app.get("/api/doctrines/export")
async def doctrines_export(ids: str = ""):
    wanted = {x for x in ids.split(",") if x}
    docs = [d for d in dstore.all_doctrines() if not wanted or str(d["id"]) in wanted]
    return dstore.export_payload(docs)


@app.post("/api/doctrines/import")
async def doctrines_import(req: Request):
    return await doctrines_import_payload(await req.json())


async def doctrines_import_payload(b):
    payload = b.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            raise HTTPException(400, "Ce texte n'est pas un export de doctrines valide.")
    incoming = dstore._normalize((payload or {}).get("doctrines"), False)
    if not incoming:
        raise HTTPException(400, "Aucune doctrine trouvée dans ce fichier.")
    docs = dstore.load_user()
    for d in incoming:
        d["id"] = os.urandom(5).hex()
        docs.append(d)
    dstore.save_user(docs)
    return {"imported": len(incoming)}


@app.post("/api/doctrines/import_file")
async def doctrines_import_file(req: Request):
    """Import d'un fichier de fits : XML (export du jeu ou de Pyfa), EFT (un ou plusieurs fits), ou export de doctrines.
    mode : "new" (une nouvelle doctrine), "prefix" (une doctrine par préfixe du nom des fits), "existing" (doctrine choisie).
    dry_run : renvoie l'aperçu sans rien enregistrer."""
    sde = need_sde()
    b = await req.json()
    content = (b.get("content") or "").lstrip("\ufeff")
    filename = os.path.basename(b.get("filename") or "fits")
    if content.strip().startswith("{"):
        if b.get("dry_run"):
            try:
                payload = json.loads(content)
            except ValueError:
                raise HTTPException(400, "Fichier JSON illisible.")
            docs = dstore._normalize(payload.get("doctrines"), False)
            return {"format": "doctrines", "preview": [{"doctrine": d["name"], "name": f["name"], "ship_type_id": f["ship_type_id"],
                                                        "ship_name": sde.name(f["ship_type_id"]), "role": f.get("role", "DPS"),
                                                        "items": len(f["items"]), "unknown": [], "duplicate": False}
                                                       for d in docs for f in d["fits"]],
                    "doctrines": [d["name"] for d in docs], "skipped": 0}
        r = await doctrines_import_payload({"payload": content})
        return {"format": "doctrines", **r}
    try:
        fmt, parsed = fitlib.parse_any(content, sde)
    except Exception as e:
        raise HTTPException(400, f"Fichier illisible : {e}")
    if not parsed:
        raise HTTPException(400, "Aucun fit trouvé dans ce fichier. Formats acceptés : XML exporté du jeu ou de Pyfa, "
                                 "texte EFT ([Vaisseau, Nom] puis les modules), export de doctrines (.json).")
    mode = b.get("mode") or "new"
    auto = b.get("auto_roles", True)
    docs = dstore.load_user()
    stem = re.sub(r"\.(xml|txt|cfg|eft)$", "", filename, flags=re.I) or "Import"
    if mode == "existing":
        target = next((d for d in docs if str(d["id"]) == str(b.get("doctrine_id"))), None)
        if target is None:
            raise HTTPException(403, "Choisis une de tes doctrines (les doctrines officielles ne sont pas modifiables).")

    def doctrine_for(prefix):
        if mode == "existing":
            return target
        name = (b.get("doctrine_name") or stem).strip() if mode == "new" else (prefix or "Autres")
        d = next((x for x in docs if x["name"].lower() == name.lower()), None) if mode == "prefix" else None
        if d is None:
            d = {"id": os.urandom(5).hex(), "name": name, "description": f"Importé depuis {filename}", "fits": [], "_new": True}
            docs.append(d)
        return d

    preview, skipped, created = [], 0, {}
    new_doc = None
    for p in parsed:
        prefix, short = fitlib.split_prefix(p["name"])
        if mode == "new":
            d = new_doc = new_doc or doctrine_for(None)
            fit_name = p["name"]
        elif mode == "prefix":
            d = created.get((prefix or "Autres").lower()) or doctrine_for(prefix)
            created[(prefix or "Autres").lower()] = d
            fit_name = short if prefix else p["name"]
        else:
            d, fit_name = target, p["name"]
        row = {"doctrine": d["name"], "name": fit_name, "ship_type_id": p["ship_type_id"],
               "ship_name": sde.name(p["ship_type_id"]) if p["ship_type_id"] else p.get("ship_name_raw", "?"),
               "role": fitlib.guess_role(sde, p["ship_type_id"], p["name"]) if auto else "DPS",
               "items": sum(i["qty"] for i in p["items"] if i["slot"] in fitlib.ESI_FLAG), "unknown": p["unknown"],
               "duplicate": False}
        if not p["ship_type_id"]:
            row["error"] = "vaisseau inconnu"
            preview.append(row)
            continue
        sig = fitlib.fit_signature(p)
        if any(fitlib.fit_signature(f) == sig for f in d["fits"]):
            row["duplicate"] = True
            skipped += 1
            preview.append(row)
            continue
        f = fitlib.new_fit({**p, "name": fit_name}, role=row["role"], notes=p.get("notes", ""))
        d["fits"].append(f)
        preview.append(row)
    touched = [d for d in docs if d.get("_new") or any(r["doctrine"] == d["name"] for r in preview)]
    if not b.get("dry_run"):
        keep = [d for d in docs if d["fits"] or not d.get("_new")]
        for d in keep:
            d.pop("_new", None)
        dstore.save_user(keep)
    return {"format": fmt, "preview": preview, "skipped": skipped,
            "added": sum(1 for r in preview if not r["duplicate"] and not r.get("error")),
            "errors": sum(1 for r in preview if r.get("error")),
            "doctrines": sorted({d["name"] for d in touched}),
            "doctrine_ids": [d["id"] for d in touched]}


@app.post("/api/doctrines/corp/refresh")
async def doctrines_corp_refresh():
    try:
        ok = await _refresh_corp_doctrines()
    except Exception as e:
        raise HTTPException(400, f"Téléchargement des doctrines corpo impossible : {e}")
    if not ok:
        raise HTTPException(400, "Aucune adresse de doctrines corpo (doctrines_url) dans distribution.json.")
    return {"ok": True}


# ---------------------------------------------------------------------- PvP : intel
zkill = pvp.ZKill(esi.client, lambda: S().get("user_agent") or "Cockpit", esi.cache)


@app.post("/api/intel/local")
async def intel_local(req: Request):
    b = await req.json()
    names = []
    for line in (b.get("text") or "").splitlines():
        n = line.strip().strip("\t")
        if n and len(n) <= 37 and n not in names:
            names.append(n)
    if not names:
        raise HTTPException(400, "Colle des noms de pilotes (un par ligne). En jeu : sélectionne les noms dans le local, Ctrl+C.")
    ids = await esi.resolve_names(names[:500])
    chars = ids["characters"]
    aff = await esi.affiliations([c["id"] for c in chars])
    aff_by = {a["character_id"]: a for a in aff}
    names_map = await esi.ids_to_names([a.get("corporation_id") for a in aff] + [a.get("alliance_id") for a in aff])
    friends_corp = {c.get("corporation_id") for c in esi.characters()}
    friends_ally = {c.get("alliance_id") for c in esi.characters() if c.get("alliance_id")}
    standings = state.get("standings") or {}
    limit = int(b.get("zkill_limit") or 60)
    stats = await asyncio.gather(*[zkill.stats("character", c["id"]) for c in chars[:limit]])
    esi.cache.flush()
    pilots = []
    for i, c in enumerate(chars):
        a = aff_by.get(c["id"], {})
        st = stats[i] if i < limit else {"found": False}
        std, std_val = pvp.classify(c["id"], a.get("corporation_id"), a.get("alliance_id"), standings,
                                    friends_corp, friends_ally)
        friendly = std in ("member", "excellent", "good")
        pilots.append({"standing": std, "standing_value": std_val,"character_id": c["id"], "name": c["name"], "corporation_id": a.get("corporation_id"),
                       "corporation": names_map.get(a.get("corporation_id"), "?"), "alliance_id": a.get("alliance_id"),
                       "alliance": names_map.get(a.get("alliance_id")) if a.get("alliance_id") else None,
                       "friendly": friendly, "stats": st, "threat": "allié" if friendly else pvp.threat_level(st)})
    groups = defaultdict(lambda: {"count": 0, "corps": defaultdict(int)})
    for p in pilots:
        key = p["alliance"] or f"(sans alliance) {p['corporation']}"
        groups[key]["count"] += 1
        groups[key]["corps"][p["corporation"]] += 1
        groups[key]["alliance_id"] = p["alliance_id"]
        groups[key]["corporation_id"] = p["corporation_id"]
        groups[key]["friendly"] = p["friendly"]
    entities = []
    for kind, lst in (("corporation", ids["corporations"]), ("alliance", ids["alliances"])):
        for e in lst[:5]:
            entities.append({"kind": kind, "id": e["id"], "name": e["name"], "stats": await zkill.stats(kind, e["id"])})
    known = {c["name"].lower() for c in chars} | {e["name"].lower() for e in ids["corporations"] + ids["alliances"]}
    return {"pilots": pilots, "unknown": [n for n in names if n.lower() not in known][:50],
            "groups": sorted([{"name": k, "count": v["count"], "alliance_id": v.get("alliance_id"),
                               "corporation_id": v.get("corporation_id"), "friendly": v.get("friendly"),
                               "corps": sorted(v["corps"].items(), key=lambda x: -x[1])} for k, v in groups.items()],
                             key=lambda g: -g["count"]),
            "entities": entities, "zkill_limited": len(chars) > limit,
            "standings_loaded": any(standings.get(k) for k in ("personal", "corp", "alliance"))}


@app.post("/api/intel/dscan")
async def intel_dscan(req: Request):
    sde = need_sde()
    b = await req.json()
    adjusted = await esi.adjusted_prices()
    res = pvp.parse_dscan(b.get("text") or "", sde, adjusted, float(b.get("grid_km") or 10_000))
    if not res["ships"] and not res["other"]:
        raise HTTPException(400, "Rien reconnu. En jeu : fenêtre D-scan (Alt+D), clic dans la liste, Ctrl+A puis Ctrl+C.")
    return res


# ---------------------------------------------------------------------- PvP : carte de la galaxie
_map_cache = {}


def _map_static():
    sde = need_sde()
    if _map_cache.get("build") == sde.build and "data" in _map_cache:
        return _map_cache["data"]
    if not sde.systems:
        raise HTTPException(409, "Carte absente des données du jeu : Réglages → Forcer la mise à jour des données du jeu.")
    systems = []
    for sid, s in sde.systems.items():
        if sid not in sde.gates:      # systèmes isolés (Jove inaccessibles…) : non affichés
            continue
        systems.append([sid, s["name"], round(s["x"] / 1e15, 4), round(-s["y"] / 1e15, 4),
                        galaxy.display_sec(s["sec"]), s["region"], s["constellation"]])
    edges = sorted({(min(a, b), max(a, b)) for a, ns in sde.gates.items() for b in ns})
    reg = {}
    for row in systems:
        r = reg.setdefault(row[5], [0.0, 0.0, 0])
        r[0] += row[2]
        r[1] += row[3]
        r[2] += 1
    regions = [{"id": rid, "name": sde.regions.get(rid, str(rid)), "x": v[0] / v[2], "y": v[1] / v[2], "n": v[2]}
               for rid, v in reg.items()]
    data = {"systems": systems, "edges": edges, "regions": sorted(regions, key=lambda r: r["name"]),
            "schematic": any(s["schematic"] for s in sde.systems.values())}
    _map_cache.update(build=sde.build, data=data)
    return data


def _jump_bridges():
    return [tuple(p) for p in (S().get("map") or {}).get("jump_bridges") or []]


async def _wormholes(sde):
    try:
        return [w for w in galaxy.parse_evescout(await esi.evescout())]
    except Exception:
        return []


def _sys_name(sde, sid):
    if sid == galaxy.THERA:
        return "Thera"
    s = sde.systems.get(sid)
    return s["name"] if s else str(sid)


@app.get("/api/map/data")
async def map_data():
    d = _map_static()
    sde = need_sde()
    jb = [[a, b] for a, b in _jump_bridges()]
    return {**d, "jump_bridges": jb, "home": sde.find_system((S().get("map") or {}).get("home") or "")}


@app.get("/api/map/live")
async def map_live():
    sde = need_sde()
    out = {"activity": {}, "sov": {}, "characters": [], "wormholes": [], "errors": []}
    try:
        out["activity"] = {k: [v["kills"], v["pods"], v["jumps"], v["npc"]] for k, v in (await esi.system_activity()).items()}
    except Exception as e:
        out["errors"].append(f"Activité : {e}")
    try:
        out["sov"] = {k: [v.get("owner", ""), v.get("alliance_id") or v.get("faction_id")] for k, v in (await esi.sovereignty()).items()}
    except Exception as e:
        out["errors"].append(f"Souveraineté : {e}")
    out["wormholes"] = await _wormholes(sde)
    for c in esi.characters():
        if "esi-location.read_location.v1" in c["missing_scopes"]:
            continue
        try:
            loc = await esi.char_location(c["character_id"])
            if loc.get("system_id"):
                out["characters"].append({"character_id": c["character_id"], "name": c["name"], **loc,
                                          "ship_type": sde.name(loc["ship_type_id"]) if loc.get("ship_type_id") else ""})
        except Exception as e:
            out["errors"].append(f"{c['name']} : {e}")
    return out


@app.get("/api/map/search")
async def map_search(q: str):
    sde = need_sde()
    ql = q.strip().lower()
    hits = sorted(((0 if s["name"].lower().startswith(ql) else 1, s["name"], sid) for sid, s in sde.systems.items()
                   if ql and ql in s["name"].lower() and sid in sde.gates))[:20]
    return [{"system_id": sid, "name": n, "region": sde.regions.get(sde.systems[sid]["region"], ""),
             "sec": galaxy.display_sec(sde.systems[sid]["sec"])} for _, n, sid in hits]


@app.get("/api/map/system/{sid}")
async def map_system(sid: int):
    sde = need_sde()
    s = sde.systems.get(sid)
    if not s:
        raise HTTPException(404, "Système inconnu.")
    region = sde.regions.get(s["region"], "")
    neighbors = [{"system_id": n, "name": _sys_name(sde, n), "sec": galaxy.display_sec(sde.systems[n]["sec"]),
                  "region": sde.regions.get(sde.systems[n]["region"], ""), "kind": "gate"}
                 for n in sorted(sde.gates.get(sid, ()), key=lambda n: sde.systems[n]["name"])]
    for a, b in _jump_bridges():
        if sid in (a, b):
            o = b if a == sid else a
            neighbors.append({"system_id": o, "name": _sys_name(sde, o), "sec": galaxy.display_sec(sde.systems[o]["sec"]),
                              "region": sde.regions.get(sde.systems[o]["region"], ""), "kind": "bridge"})
    wh = [w for w in await _wormholes(sde) if w["system_id"] == sid]
    return {"system_id": sid, "name": s["name"], "region": region, "region_id": s["region"],
            "constellation": sde.constellations.get(s["constellation"], ""), "sec": galaxy.display_sec(s["sec"]),
            "sec_raw": s["sec"], "sec_class": galaxy.sec_class(s["sec"]), "neighbors": neighbors, "wormholes": wh,
            "links": {"dotlan": galaxy.dotlan_system(s["name"]), "dotlan_region": galaxy.dotlan_region(region, s["name"]),
                      "zkill": galaxy.zkill_system(sid)}}


@app.get("/api/map/route")
async def map_route(src: str, dst: str, mode: str = "shortest", avoid: str = "", jb: bool = True, wh: bool = False):
    sde = need_sde()
    a, b = sde.find_system(src), sde.find_system(dst)
    if not a or not b:
        raise HTTPException(400, f"Système inconnu : {src if not a else dst}")
    avoid_ids = {sde.find_system(x) for x in re.split(r"[,\n]", avoid) if x.strip()} - {None}
    worms = await _wormholes(sde) if wh else []
    graph = galaxy.build_graph(sde, _jump_bridges() if jb else (), [(w["system_id"], w["hub_id"]) for w in worms])
    path = galaxy.route(graph, sde, a, b, mode, avoid_ids)
    if not path:
        raise HTTPException(404, "Aucun itinéraire trouvé avec ces options (systèmes évités, mode).")
    try:
        act = await esi.system_activity()
    except Exception:
        act = {}
    steps = []
    for i, sid in enumerate(path):
        s = sde.systems.get(sid)
        via = graph.get(path[i - 1], {}).get(sid) if i else None
        steps.append({"system_id": sid, "name": _sys_name(sde, sid), "sec": galaxy.display_sec(s["sec"]) if s else -1.0,
                      "sec_class": galaxy.sec_class(s["sec"]) if s else "wh",
                      "region": sde.regions.get(s["region"], "") if s else "Espace W",
                      "kills": (act.get(sid) or {}).get("kills", 0), "pods": (act.get(sid) or {}).get("pods", 0),
                      "jumps": (act.get(sid) or {}).get("jumps", 0), "via": via})
    names = [x["name"] for x in steps]
    return {"path": path, "steps": steps, "jumps": len(path) - 1,
            "counts": {k: sum(1 for x in steps[1:] if x["sec_class"] == k) for k in ("high", "low", "null", "wh")},
            "bridges": sum(1 for x in steps if x["via"] == "bridge"), "wormholes": sum(1 for x in steps if x["via"] == "wormhole"),
            "kills": sum(x["kills"] for x in steps), "dotlan": galaxy.dotlan_route([names[0], names[-1]])}


@app.get("/api/map/nearby")
async def map_nearby(system: str, jumps: int = 5, gates_only: bool = False):
    sde = need_sde()
    sid = sde.find_system(system)
    if not sid:
        raise HTTPException(400, f"Système inconnu : {system}")
    graph = galaxy.build_graph(sde, () if gates_only else _jump_bridges())
    near = galaxy.within_jumps(graph, sid, max(0, min(int(jumps), 15)))
    return [{"system_id": k, "name": _sys_name(sde, k), "jumps": v} for k, v in sorted(near.items(), key=lambda x: (x[1], _sys_name(sde, x[0])))]


@app.post("/api/map/waypoint")
async def map_waypoint(req: Request):
    b = await req.json()
    try:
        await esi.set_waypoint(int(b["character_id"]), int(b["system_id"]), clear=b.get("clear", True))
    except EsiError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/map/jump_bridges/import")
async def map_jump_bridges_import(req: Request):
    """Lit les ponts Ansiblex accessibles par les personnages connectés et les ajoute à la liste."""
    sde = need_sde()
    b = await req.json() if (await req.body()) else {}
    chars = [c for c in esi.characters() if not b.get("character_id") or c["character_id"] == int(b["character_id"])]
    if not chars:
        raise HTTPException(400, "Connecte d'abord un personnage (Personnages & stock).")
    found, errors = [], []
    for c in chars:
        try:
            found += await esi.ansiblex(c["character_id"])
        except Exception as e:
            errors.append(f"{c['name']} : {e}")
    new = galaxy.ansiblex_pairs(found, sde)
    m = dict(S().get("map") or {})
    pairs = [tuple(p) for p in m.get("jump_bridges") or []] if not b.get("replace") else []
    added = 0
    for a, z in new:
        if (a, z) not in pairs and (z, a) not in pairs:
            pairs.append((a, z))
            added += 1
    m.update(jump_bridges=[list(p) for p in pairs], jb_text=galaxy.pairs_text(pairs, sde))
    state["settings"]["map"] = m
    save_settings(state["settings"])
    if not found and not errors:
        errors.append("Aucun pont trouvé : ton personnage doit avoir accès aux ponts de l'alliance (liste d'accès), "
                      "sinon colle la liste à la main.")
    return {"found": len(found), "pairs": len(new), "added": added, "total": len(pairs), "errors": errors,
            "text": m["jb_text"]}


@app.post("/api/map/jump_bridges")
async def map_jump_bridges(req: Request):
    sde = need_sde()
    b = await req.json()
    pairs, bad = galaxy.parse_jump_bridges(b.get("text") or "", sde)
    m = dict(S().get("map") or {})
    m.update(jump_bridges=[list(p) for p in pairs], jb_text=b.get("text") or "")
    if "home" in b:
        m["home"] = b["home"]
    state["settings"]["map"] = m
    save_settings(state["settings"])
    return {"count": len(pairs), "bad": bad[:30]}


# ---------------------------------------------------------------------- Soutenir Cockpit (dons en ISK)
@app.get("/api/donate")
async def donate_info():
    name = distribution().get("donate_character") or S().get("donate_character") or "Robapin"
    key = f"donate:{name}"
    c = esi.cache.get(key, 86400)
    if c is None:
        try:
            ids = await esi.resolve_names([name])
            ch = (ids.get("characters") or [None])[0]
            c = {"name": ch["name"], "character_id": ch["id"]} if ch else {"name": name, "character_id": None}
            if ch:
                aff = await esi.affiliations([ch["id"]])
                if aff:
                    names = await esi.ids_to_names([aff[0].get("corporation_id"), aff[0].get("alliance_id")])
                    c.update(corporation=names.get(aff[0].get("corporation_id")), alliance=names.get(aff[0].get("alliance_id")),
                             corporation_id=aff[0].get("corporation_id"))
            esi.cache.set(key, c)
            esi.cache.flush()
        except Exception:
            c = {"name": name, "character_id": None}
    return c


@app.post("/api/donate/open")
async def donate_open(req: Request):
    b = await req.json()
    info = await donate_info()
    if not info.get("character_id"):
        raise HTTPException(400, "Personnage introuvable pour le moment (ESI injoignable ?). Cherche son nom en jeu.")
    try:
        await esi.open_info_window(int(b["character_id"]), info["character_id"])
    except EsiError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------------------------------------------------------------------- Planétaire (PI)
_pi_cache = {}


def _pi():
    sde = need_sde()
    if not sde.pi_schematics or not sde.planets:
        raise HTTPException(409, "Données planétaires absentes : Réglages → Forcer la mise à jour des données du jeu.")
    if _pi_cache.get("build") != sde.build:
        _pi_cache.update(build=sde.build, pi=planetary.PI(sde))
    return _pi_cache["pi"]


async def _pi_prices(pi):
    ids = set(pi.products()) | set(pi.p0_ids.values())
    main = all_markets(S()).get(S().get("price_market") or "jita") or HUBS["jita"]
    try:
        return await esi.market_prices(main, ids), main.get("short") or main.get("name")
    except Exception:
        return {}, None


def _pi_center(sde, system):
    sid = sde.find_system(system or "")
    if not sid:
        raise HTTPException(400, f"Système inconnu : {system}")
    return sid


@app.get("/api/pi/area")
async def pi_area(system: str, jumps: int = 3):
    pi = _pi()
    sde = need_sde()
    center = _pi_center(sde, system)
    prices, market = await _pi_prices(pi)
    res = pi.analyze(center, max(0, min(int(jumps), 15)), prices, _jump_bridges())
    for s in res["systems"]:
        sys_ = sde.systems[s["system_id"]]
        s.update(name=sys_["name"], sec=galaxy.display_sec(sys_["sec"]), region=sde.regions.get(sys_["region"], ""))
    res.update(center_name=sde.systems[center]["name"], market=market)
    return res


@app.get("/api/pi/product/{tid}")
async def pi_product(tid: int, system: str, jumps: int = 3):
    pi = _pi()
    sde = need_sde()
    if tid not in sde.pi_producer:
        raise HTTPException(404, "Ce n'est pas un produit planétaire.")
    center = _pi_center(sde, system)
    prices, market = await _pi_prices(pi)
    sch = sde.pi_schematics[sde.pi_producer[tid]]
    return {"type_id": tid, "name": sde.name(tid), "tier": pi.tier(tid), "cycle_s": sch["cycle"],
            "out_qty": sch["out"][1], "inputs": [{"type_id": i, "name": sde.name(i), "qty": q,
                                                  "price": (prices.get(i) or {}).get("sell") or 0} for i, q in sch["in"]],
            "price": (prices.get(tid) or {}).get("sell") or 0, "market": market,
            "tree": pi.tree(tid, 1), "p0": [{"type_id": x, "name": sde.name(x), "planets": pi.p0_planets(x)}
                                           for x in sorted(pi.p0_needed(tid), key=sde.name)],
            "best": pi.best_systems(tid, center, max(0, min(int(jumps), 15)), _jump_bridges())}


@app.get("/api/pi/system/{sid}")
async def pi_system(sid: int):
    pi = _pi()
    sde = need_sde()
    if sid not in sde.systems:
        raise HTTPException(404, "Système inconnu.")
    s = sde.systems[sid]
    return {"system_id": sid, "name": s["name"], "sec": galaxy.display_sec(s["sec"]),
            "region": sde.regions.get(s["region"], ""), "planets": pi.system_planets(sid),
            "dotlan": galaxy.dotlan_system(s["name"])}


# ---------------------------------------------------------------------- PvP : alarme de local / intel
alarm = alarmlib.Alarm(lambda: state["settings"])


@app.get("/api/alarm/monitors")
async def alarm_monitors():
    try:
        return await asyncio.to_thread(alarmlib.Alarm.monitors)
    except Exception as e:
        raise HTTPException(400, f"Capture d'écran impossible : {e}")


@app.get("/api/alarm/screenshot")
async def alarm_screenshot(monitor: int = 1):
    try:
        png, _geo = await asyncio.to_thread(alarmlib.Alarm.screenshot_png, monitor)
    except Exception as e:
        raise HTTPException(400, f"Capture d'écran impossible : {e}")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/alarm/status")
async def alarm_status():
    return alarm.status()


@app.post("/api/alarm/start")
async def alarm_start():
    c = S().get("alarm") or {}
    zone = c.get("region_rel") if c.get("source", "window") == "window" else c.get("region")
    local_ok = c.get("screen_enabled") and zone and (c.get("detection", "auto") == "auto" or c.get("colors"))
    intel_ok = c.get("logs_enabled") and c.get("channels")
    if not (local_ok or intel_ok):
        raise HTTPException(400, "Rien à surveiller : prends la photo et encadre ton local (étape 2), "
                                 "ou configure l'alarme intel.")
    await alarm.start()
    return {"ok": True}


@app.get("/api/alarm/windows")
async def alarm_windows():
    try:
        wins = await asyncio.to_thread(alarm.backend.list_windows)
    except Exception as e:
        raise HTTPException(400, f"Lecture des fenêtres impossible : {e}")
    return {"supported": alarm.backend.available(), "windows": wins}


@app.get("/api/alarm/window_shot")
async def alarm_window_shot(hwnd: int):
    try:
        png = await asyncio.to_thread(alarm.window_png, hwnd)
    except Exception as e:
        raise HTTPException(400, f"Capture de la fenêtre impossible : {e}")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/alarm/analyze")
async def alarm_analyze(req: Request):
    """Analyse instantanée de la zone encadrée : icônes trouvées par couleur (pour la photo de réglage)."""
    b = await req.json()
    rel = b.get("rel") or {}

    def run():
        if b.get("hwnd"):
            arr = alarm.backend.capture(int(b["hwnd"]))
        else:
            import mss
            import numpy as np
            with mss.mss() as sct:
                mon = sct.monitors[int(b.get("monitor") or 1)]
                img = sct.grab(mon)
                arr = np.frombuffer(img.bgra, dtype=np.uint8).reshape(img.height, img.width, 4)
        return alarm.analyze(alarmlib.crop(arr, rel), S().get("alarm") or {})

    try:
        return await asyncio.to_thread(run)
    except Exception as e:
        raise HTTPException(400, f"Analyse impossible : {e}")


@app.post("/api/alarm/check")
async def alarm_check():
    try:
        return await asyncio.to_thread(alarm.check_now)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/alarm/sounds")
async def alarm_sounds():
    return soundlib.SOUNDS


@app.get("/api/alarm/sound")
async def alarm_sound(name: str = "bip", volume: int = 70):
    return Response(soundlib.wav(name, volume), media_type="audio/wav", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/alarm/stop")
async def alarm_stop():
    await alarm.stop()
    return {"ok": True}


@app.post("/api/alarm/rearm")
async def alarm_rearm():
    alarm.rearm()
    return {"ok": True}


@app.post("/api/alarm/test")
async def alarm_test(req: Request):
    b = await req.json() if (await req.body()) else {}
    level = b.get("level", "rouge")
    kind = "intel" if level == "intel" else "test"
    alarm.push(kind, level if level != "intel" else "orange", f"Test du son « {level} »")
    return {"ok": True}


@app.get("/api/alarm/channels")
async def alarm_channels():
    c = S().get("alarm") or {}
    dirs = alarmlib.chatlog_dirs()
    d = c.get("log_dir") or (dirs[0] if dirs else "")
    chans = alarmlib.list_channels(d) if d and os.path.isdir(d) else {}
    return {"dir": d, "found_dirs": dirs, "exists": bool(d and os.path.isdir(d)),
            "channels": [{"name": k, "last": v} for k, v in chans.items()]}


# ---------------------------------------------------------------------- interface
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
