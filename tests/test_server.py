"""Test bout-en-bout de l'API avec des données simulées (pas de réseau)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import server
from app.sde import SDE
from tests.fixture import make_zip, price_book_data
from tests.test_engine import NULL_RAITARU, NULL_TATARA


@pytest.fixture
def client(monkeypatch, tmp_path):
    prices, adjusted, indices = price_book_data()
    monkeypatch.setattr(server, "save_settings", lambda s: None)
    monkeypatch.setattr(server, "_save_account", lambda: None)
    from app import doctrines as dstore
    monkeypatch.setattr(dstore, "USER_PATH", str(tmp_path / "doctrines.json"))
    monkeypatch.setattr(dstore, "CORP_CACHE", str(tmp_path / "corp.json"))
    server.state["sde"] = SDE.from_zip_bytes(make_zip(), "test")
    server.state["settings"]["structures"] = [NULL_RAITARU, NULL_TATARA]

    async def mp(market, ids):
        return {t: prices[t] for t in ids if t in prices}

    async def adj():
        return adjusted

    async def idx():
        return indices

    async def hist(region, ids, progress=None):
        return {t: {"daily_volume": 50, "avg_price_7d": 1, "days": 30} for t in ids}

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(server.esi, "market_prices", mp)
    monkeypatch.setattr(server.esi, "adjusted_prices", adj)
    monkeypatch.setattr(server.esi, "cost_indices", idx)
    monkeypatch.setattr(server.esi, "histories", hist)
    monkeypatch.setattr(server, "_sde_update", nothing)
    monkeypatch.setattr(server, "_startup_tasks", nothing)
    with TestClient(server.app) as c:
        yield c


def test_endpoints(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/status").json()["sde_loaded"]
    assert client.get("/api/search?q=wol").json()[0]["name"] == "Wolf"
    r = client.post("/api/plan", json={"type_id": 11371, "quantity": 12, "optimize": True})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["summary"]["total_cost"] > 0 and j["jobs"] and j["buy"]
    r = client.post("/api/plan", json={"type_id": 11371, "quantity": 5, "decryptor": "Accelerant Decryptor",
                                       "compare_market": "amarr"})
    j = r.json()
    assert j["inventions"][0]["decryptor"] == "Accelerant Decryptor"
    assert "compare_price" in j["buy"][0]
    inv = client.get("/api/invention/11371").json()
    assert len(inv["rows"]) == 9
    assert client.get("/api/invention/587").status_code == 400
    client.post("/api/scan/start")
    for _ in range(50):
        s = client.get("/api/scan/status").json()
        if not s["running"]:
            break
        time.sleep(0.1)
    assert s["error"] is None, s["error"]
    assert s["result"]["rows"]


def test_arbitrage(client, monkeypatch):
    async def ti(t):
        return {"packaged_volume": 0.01}

    async def mh(region, t):
        return {"daily_volume": 1000, "avg_price_7d": 1, "days": 30}

    async def mp2(market, ids):
        base = {587: 600_000, 11371: 30_000_000}
        f = 1.0 if market["id"] == "jita" else 1.4
        return {t: {"sell": v * f, "buy": v * f * 0.95, "sell_vol": 100, "buy_vol": 100} for t, v in base.items()}

    monkeypatch.setattr(server.esi, "type_info", ti)
    monkeypatch.setattr(server.esi, "market_history", mh)
    monkeypatch.setattr(server.esi, "market_prices", mp2)
    server.state["settings"]["arbitrage"]["hubs"] = ["jita", "amarr"]
    client.post("/api/arbitrage/start")
    for _ in range(50):
        s = client.get("/api/arbitrage/status").json()
        if not s["running"]:
            break
        time.sleep(0.1)
    assert s["error"] is None, s["error"]
    rows = s["result"]["rows"]
    assert rows and rows[0]["from"] == "Jita" and rows[0]["to"] == "Amarr"


def test_stock_excludes_fitted_and_assembled(client):
    server.state["assets"] = {"char:1": [
        {"type_id": 34, "quantity": 1000, "location_flag": "Hangar", "is_singleton": False, "root_location": 60003760},
        {"type_id": 587, "quantity": 1, "location_flag": "Hangar", "is_singleton": True, "root_location": 60003760},
        {"type_id": 11541, "quantity": 3, "location_flag": "HiSlot0", "is_singleton": True, "root_location": 60003760},
        {"type_id": 35, "quantity": 50, "location_flag": "Hangar", "is_singleton": False, "root_location": 1},
    ]}
    st = server.stock_from_sources({"characters": [1], "corp_divisions": [], "location_ids": [60003760]})
    assert dict(st) == {34: 1000}
    server.state["assets"] = {}


def test_multi_plan_api_and_lang(client):
    server.state["settings"]["lang"] = "fr"
    server._apply_lang()
    r = client.post("/api/plan", json={"items": [{"type_id": 11371, "quantity": 2}, {"type_id": 11541, "quantity": 10}]})
    assert r.status_code == 200, r.text
    names = {n["name"] for n in r.json()["nodes"]}
    assert "Propulseur à fusion" in names
    assert client.get("/api/search?q=propul").json()[0]["type_id"] == 11541
    server.state["settings"]["lang"] = "en"
    server._apply_lang()
    st = client.get("/api/status").json()
    assert "esi-assets.read_assets.v1" in st["scopes"] and "callback_url" in st


def test_pvp_doctrines_api(client, monkeypatch):
    from tests.test_pvp import EFT
    monkeypatch.setattr(server.esi, "characters", lambda: [
        {"character_id": 7, "name": "Pilote Test", "corporation_id": 99, "alliance_id": 500, "missing_scopes": []}])
    server.state["char_skills"][7] = {3329: 5, 3300: 5, 3302: 4}
    server.state["char_attrs"][7] = {"perception": 20, "willpower": 20}
    did = client.post("/api/doctrines", json={"name": "Brawl"}).json()["id"]
    r = client.post(f"/api/doctrines/{did}/fits", json={"eft": EFT, "role": "DPS"}).json()
    assert r["added"] == ["Wolf brawl"] and not r["warnings"]
    docs = client.get("/api/doctrines").json()["doctrines"]
    fit = docs[0]["fits"][0]
    assert fit["ship_name"] == "Wolf" and fit["pilots"][0]["can_fly"] is False
    det = client.get(f"/api/fits/{fit['id']}").json()
    assert det["total"] > 30_000_000 and det["pilots"][0]["missing"]
    assert "Assault Frigates I" in det["pilots"][0]["plan"]
    assert det["eft"].startswith("[Wolf, Wolf brawl]")
    order = client.post(f"/api/doctrines/{did}/order", json={"quantities": {fit["id"]: 5}}).json()
    hull = next(x for x in order["rows"] if x["type_id"] == 11371)
    assert hull["to_buy"] == 5 and hull["buildable"] and order["rows"][0]["is_hull"]
    cannons = next(x for x in order["rows"] if x["type_id"] == 2889)
    assert cannons["needed"] == 15
    rep = client.get(f"/api/doctrines/{did}/report").json()["text"]
    assert "Pilote Test" in rep and "❌" in rep
    exp = client.get("/api/doctrines/export").json()
    assert exp["doctrines"][0]["fits"][0]["ship_type_id"] == 11371
    assert client.post("/api/doctrines/import", json={"payload": exp}).json()["imported"] == 1
    assert len(client.get("/api/doctrines").json()["doctrines"]) == 2
    client.put(f"/api/fits/{fit['id']}", json={"role": "Tackle", "notes": "point + scram"})
    assert client.get(f"/api/fits/{fit['id']}").json()["role"] == "Tackle"
    assert client.delete(f"/api/fits/{fit['id']}").json()["ok"]
    server.state["char_skills"].pop(7, None)


def test_official_doctrine_readonly(client, monkeypatch):
    from app import doctrines as dstore
    monkeypatch.setattr(dstore, "distribution", lambda: {"doctrines": [{"id": "vx", "name": "Vexor corpo", "fits": []}]})
    docs = client.get("/api/doctrines").json()["doctrines"]
    off = next(d for d in docs if d["official"])
    assert off["id"] == "corp-vx"
    assert client.post(f"/api/doctrines/{off['id']}/fits", json={"eft": "[Wolf, x]"}).status_code == 403
    new_id = client.post(f"/api/doctrines/{off['id']}/duplicate").json()["id"]
    assert client.post(f"/api/doctrines/{new_id}/fits", json={"eft": "[Wolf, x]\nDamage Control II"}).status_code == 200


def test_intel_endpoints(client, monkeypatch):
    async def resolve(names):
        return {"characters": [{"id": 1, "name": "Méchant"}, {"id": 2, "name": "Copain"}], "corporations": [], "alliances": []}

    async def aff(ids):
        return [{"character_id": 1, "corporation_id": 10, "alliance_id": 100},
                {"character_id": 2, "corporation_id": 99}]

    async def names(ids):
        return {10: "Pirates Inc", 100: "Bad Alliance", 99: "Section XIII"}

    async def stats(kind, eid):
        from app.pvp import summarize_zkb
        return summarize_zkb({"shipsDestroyed": 300, "shipsLost": 10, "dangerRatio": 90, "activepvp": {"kills": {"count": 20}}})

    monkeypatch.setattr(server.esi, "resolve_names", resolve)
    monkeypatch.setattr(server.esi, "affiliations", aff)
    monkeypatch.setattr(server.esi, "ids_to_names", names)
    monkeypatch.setattr(server.zkill, "stats", stats)
    monkeypatch.setattr(server.esi, "characters", lambda: [{"character_id": 7, "name": "Moi", "corporation_id": 99}])
    r = client.post("/api/intel/local", json={"text": "Méchant\nCopain\nInconnu"}).json()
    by = {p["name"]: p for p in r["pilots"]}
    assert by["Méchant"]["threat"] == "très dangereux" and by["Copain"]["friendly"]
    assert r["unknown"] == ["Inconnu"] and r["groups"][0]["count"] == 1
    d = client.post("/api/intel/dscan", json={"text": "Sabre\tSabre\t100 km\nScimitar\tScimitar\t-"}).json()
    assert d["total_ships"] == 2 and d["on_grid"] == 1
    assert client.post("/api/intel/dscan", json={"text": "rien"}).status_code == 400
    v = client.get("/api/version").json()
    assert v["version"] == v["changelog"][0]["version"]


def test_import_file_xml(client):
    from tests.test_pvp import XML
    # aperçu : rien n'est enregistré
    prev = client.post("/api/doctrines/import_file", json={"filename": "corpo.xml", "content": XML, "mode": "prefix", "dry_run": True}).json()
    assert prev["format"] == "xml" and prev["added"] == 3 and set(prev["doctrines"]) == {"Wolf", "Sabre"}
    assert client.get("/api/doctrines").json()["doctrines"] == []
    roles = {r["name"]: r["role"] for r in prev["preview"]}
    assert roles == {"DPS": "DPS", "Tackle": "Tackle", "Bulle": "Tackle"}   # rôle deviné : nom du fit, puis vaisseau
    r = client.post("/api/doctrines/import_file", json={"filename": "corpo.xml", "content": XML, "mode": "prefix"}).json()
    docs = {d["name"]: d for d in client.get("/api/doctrines").json()["doctrines"]}
    assert [f["name"] for f in docs["Wolf"]["fits"]] == ["DPS", "Tackle"] and len(docs["Sabre"]["fits"]) == 1
    # réimporter : tout est reconnu comme doublon
    again = client.post("/api/doctrines/import_file", json={"filename": "corpo.xml", "content": XML, "mode": "prefix"}).json()
    assert again["added"] == 0 and again["skipped"] == 3
    # mode « nouvelle doctrine » : un seul conteneur nommé d'après le fichier
    one = client.post("/api/doctrines/import_file", json={"filename": "Doctrines corpo.xml", "content": XML, "mode": "new"}).json()
    assert one["doctrines"] == ["Doctrines corpo"] and one["added"] == 3
    # mode « doctrine existante »
    did = docs["Sabre"]["id"]
    eft = "[Wolf, Nouveau]\nDamage Control II\n200mm AutoCannon II"
    ex = client.post("/api/doctrines/import_file", json={"filename": "a.txt", "content": eft, "mode": "existing", "doctrine_id": did}).json()
    assert ex["format"] == "eft" and ex["added"] == 1
    assert client.post("/api/doctrines/import_file", json={"filename": "x.xml", "content": "rien"}).status_code == 400


def test_map_api(client, monkeypatch):
    async def act():
        return {30005196: {"kills": 7, "pods": 2, "npc": 0, "jumps": 40}}

    async def sov():
        return {30004759: {"alliance_id": 1, "owner": "Goonswarm"}}

    async def scout():
        return [{"out_system_id": 31000005, "out_system_name": "Thera", "in_system_id": 30000144, "in_system_name": "Perimeter"},
                {"out_system_id": 31000005, "out_system_name": "Thera", "in_system_id": 30004807, "in_system_name": "T5ZI-S"}]

    monkeypatch.setattr(server.esi, "system_activity", act)
    monkeypatch.setattr(server.esi, "sovereignty", sov)
    monkeypatch.setattr(server.esi, "evescout", scout)
    server._map_cache.clear()
    d = client.get("/api/map/data").json()
    assert len(d["systems"]) == 8 and len(d["edges"]) == 9          # le système isolé n'est pas affiché
    assert client.get("/api/map/search?q=jit").json()[0]["name"] == "Jita"
    sysd = client.get("/api/map/system/30005196").json()
    assert sysd["region"] == "The Citadel" and sysd["sec_class"] == "low" and len(sysd["neighbors"]) == 3
    assert sysd["links"]["dotlan"].endswith("/system/Ahbazon")
    r = client.get("/api/map/route?src=Jita&dst=Ahbazon&mode=secure").json()
    assert r["jumps"] == 3 and r["counts"]["low"] == 1 and r["kills"] == 7
    r2 = client.get("/api/map/route?src=Perimeter&dst=T5ZI-S&wh=true").json()
    assert [s["name"] for s in r2["steps"]] == ["Perimeter", "Thera", "T5ZI-S"] and r2["wormholes"] == 2
    assert client.get("/api/map/route?src=Jita&dst=Nulle-part").status_code == 400
    jb = client.post("/api/map/jump_bridges", json={"text": "Jita » 1DQ1-A\nfaux"}).json()
    assert jb["count"] == 1 and jb["bad"] == ["faux"]
    assert client.get("/api/map/route?src=Jita&dst=1DQ1-A").json()["bridges"] == 1
    assert client.get("/api/map/route?src=Jita&dst=1DQ1-A&jb=false").json()["jumps"] == 3
    near = client.get("/api/map/nearby?system=1DQ1-A&jumps=1").json()
    assert {n["name"] for n in near} == {"1DQ1-A", "T5ZI-S", "Ahbazon", "Jita"}
    live = client.get("/api/map/live").json()
    assert live["activity"]["30005196"][0] == 7 and live["sov"]["30004759"][0] == "Goonswarm"
    assert len(live["wormholes"]) == 2
    server.state["settings"]["map"] = {"jump_bridges": [], "jb_text": "", "home": ""}


def test_alarm_api(client):
    assert client.get("/api/alarm/sound?name=sonar&volume=40").content[:4] == b"RIFF"
    assert "sirene" in client.get("/api/alarm/sounds").json()
    w = client.get("/api/alarm/windows").json()
    assert isinstance(w["supported"], bool) and w["windows"] == []
    assert client.post("/api/alarm/test", json={"level": "intel"}).json()["ok"]
    ev = client.get("/api/alarm/status").json()["events"][0]
    assert ev["sound"] == "cloche"


def test_bridges_import_and_sov(client, monkeypatch):
    monkeypatch.setattr(server.esi, "characters", lambda: [{"character_id": 7, "name": "Moi", "missing_scopes": []}])

    async def ansi(cid):
        return [{"structure_id": 1, "name": "1DQ1-A » T5ZI-S - Pont", "system_id": 30004759},
                {"structure_id": 2, "name": "T5ZI-S » 1DQ1-A - Pont", "system_id": 30004807}]

    monkeypatch.setattr(server.esi, "ansiblex", ansi)
    server.state["settings"]["map"] = {"jump_bridges": [], "jb_text": "", "home": ""}
    r = client.post("/api/map/jump_bridges/import", json={}).json()
    assert r["found"] == 2 and r["pairs"] == 1 and r["total"] == 1 and "1DQ1-A » T5ZI-S" in r["text"]
    assert client.post("/api/map/jump_bridges/import", json={}).json()["added"] == 0      # pas de doublon
    server.state["settings"]["map"] = {"jump_bridges": [], "jb_text": "", "home": ""}


def test_pi_api(client):
    a = client.get("/api/pi/area?system=Jita&jumps=2").json()
    assert a["center_name"] == "Jita" and a["planets"] >= 5 and any(p["feasible"] for p in a["products"])
    p = client.get("/api/pi/product/2867?system=Jita&jumps=2").json()
    assert p["tier"] == 4 and p["best"][0]["name"] == "Jita" and p["tree"]["children"]
    s = client.get("/api/pi/system/30000142").json()
    assert s["planets"][0]["name"] == "Jita I"
    assert client.get("/api/pi/area?system=Nulle&jumps=2").status_code == 400


def test_translations_and_donate(client, monkeypatch):
    """Le dictionnaire de traduction est valide et couvre le menu ; la page de dons répond."""
    import json, os, re
    path = os.path.join(os.path.dirname(__file__), "..", "static", "i18n-data.js")
    s = open(path, encoding="utf-8").read()
    data = json.loads(s[s.index("window.I18N_DATA =") + len("window.I18N_DATA ="):s.rindex(";")])
    html = open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"), encoding="utf-8").read()
    nav = [re.sub(r"<[^>]+>.*", "", m).strip() for m in re.findall(r'data-view="[^"]+"[^>]*>([^<]+)', html)]
    for lang in ("en", "es", "de", "ru"):
        missing = [n for n in nav if n and n not in data[lang]]
        assert not missing, (lang, missing)

    async def resolve(names):
        return {"characters": [{"id": 95465499, "name": "Robapin"}], "corporations": [], "alliances": []}

    async def aff(ids):
        return []

    monkeypatch.setattr(server.esi, "resolve_names", resolve)
    monkeypatch.setattr(server.esi, "affiliations", aff)
    server.esi.cache.data.pop("donate:Robapin", None)
    d = client.get("/api/donate").json()
    assert d["name"] == "Robapin" and d["character_id"] == 95465499
