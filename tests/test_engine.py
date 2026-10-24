import copy
import math

import pytest

from app.industry import Engine, PriceBook
from app.opportunities import all_inputs, candidate_products, finalize_industry, score_industry
from app.sde import SDE
from app.settings import DEFAULTS
from tests.fixture import make_zip, price_book_data

NULL_RAITARU = {"id": "r1", "name": "Raitaru null", "kind": "Raitaru", "system_id": 30004759, "security": "null",
                "tax_pct": 1.0, "activities": ["manufacturing", "invention", "copying"],
                "rigs": [{"applies": "basic_small_ship", "me": 2.4, "te": 24}]}
NULL_TATARA = {"id": "t1", "name": "Tatara null", "kind": "Tatara", "system_id": 30004759, "security": "null",
               "tax_pct": 1.0, "activities": ["reaction"], "rigs": [{"applies": "reactions", "me": 2.4, "te": 24}]}


@pytest.fixture
def sde():
    return SDE.from_zip_bytes(make_zip(), "test")


def engine(sde, structures=(), **over):
    s = copy.deepcopy(DEFAULTS)
    s["structures"] = list(structures)
    s.update(over)
    p, a, i = price_book_data()
    return Engine(sde, s, PriceBook(s, p, a, i))


def test_sde_parsing(sde):
    assert sde.name(587) == "Rifter"
    assert sde.producer[587] == (691, "manufacturing", 1)
    assert sde.producer[16670] == (99002, "reaction", 10000)
    assert sde.invented_from[11372] == (691, 10, 0.34)
    assert sde.is_t2(11371) and not sde.is_t2(587)
    assert sde.search("rif")[0]["name"] == "Rifter"


def test_material_formula(sde):
    e = engine(sde, [NULL_RAITARU])
    st, mm, _ = e.best_structure(587)
    # ME10 * rôle Raitaru 1 % * rig T2 2,4 % x 2,1 (nullsec)
    expected = 0.9 * 0.99 * (1 - 2.4 * 2.1 / 100)
    assert mm == pytest.approx(expected)
    assert e.job_quantity(30000, 10, mm) == math.ceil(round(10 * 30000 * expected, 2))
    # une quantité de base de 1 ne descend jamais sous le nombre de runs
    assert e.job_quantity(1, 10, mm) == 10


def test_job_cost(sde):
    e = engine(sde, [NULL_RAITARU])
    eiv = e.eiv([(34, 30000), (35, 6000), (36, 2500)], 1)
    assert eiv == 30000 * 4 + 6000 * 10 + 2500 * 60
    cost = e.job_cost(eiv, NULL_RAITARU, "manufacturing")
    assert cost == pytest.approx(eiv * 0.02 * 0.97 + eiv * (1.0 + 4.0) / 100)


def test_invention_probability(sde):
    e = engine(sde, [NULL_RAITARU])
    info = e.invention_info(11371)
    # niveaux par défaut : science 4/4, encryption 4
    assert info["probability"] == pytest.approx(0.34 * (1 + 8 / 30 + 4 / 40))
    assert info["runs"] == 10
    acc = e.invention_info(11371, "Accelerant Decryptor")
    assert acc["probability"] == pytest.approx(0.34 * (1 + 8 / 30 + 4 / 40) * 1.2)
    assert acc["runs"] == 11
    assert e.bp_me_te(11372, "manufacturing", "Accelerant Decryptor") == (4, 14)


def test_plan_full_tree(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    res = e.plan(11371, 10, optimize=False)
    names = {j["name"] for j in res["jobs"]}
    assert {"Wolf", "Rifter", "Fusion Thruster", "Crystalline Carbonide"} <= names
    buy = {b["name"]: b for b in res["buy"]}
    assert "Tritanium" in buy and "Atmospheric Gases" in buy
    assert "Datacore - Mechanical Engineering" in buy
    # les jobs sont triés du plus profond (à lancer en premier) au produit final
    depths = [j["depth"] for j in res["jobs"]]
    assert depths == sorted(depths, reverse=True)
    assert res["jobs"][-1]["name"] == "Wolf"
    # 10 Wolf = 1 BPC de 10 runs ; tentatives = ceil(1 / p)
    inv = res["inventions"][0]
    assert inv["bpcs_needed"] == 1 and inv["attempts"] == math.ceil(1 / inv["probability"])
    # la réaction est faite dans la Tatara
    carb = next(j for j in res["jobs"] if j["name"] == "Crystalline Carbonide")
    assert carb["structure"] == "Tatara null"
    s = res["summary"]
    assert s["total_cost"] > 0 and s["revenue_net"] > 0
    assert s["profit"] == pytest.approx(s["revenue_net"] - s["total_cost"])


def test_optimize_buys_when_cheaper(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    # Fusion Thruster très bon marché sur le marché -> l'optimiseur l'achète
    e.p.prices[11541] = {"sell": 1, "buy": 1}
    res = e.plan(11371, 10, optimize=True)
    names = {j["name"] for j in res["jobs"]}
    assert "Fusion Thruster" not in names
    assert any(b["name"] == "Fusion Thruster" for b in res["buy"])


def test_overrides_and_stock(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    res = e.plan(11371, 10, overrides={587: "buy"}, stock={34: 1_000_000_000})
    assert not any(j["name"] == "Rifter" for j in res["jobs"])
    trit = next(b for b in res["buy"] if b["name"] == "Tritanium")
    assert trit["to_buy"] == 0 and trit["in_stock"] == trit["needed"]


def test_job_split_on_max_runs(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    res = e.plan(11371, 25)
    wolf_jobs = [j for j in res["jobs"] if j["name"] == "Wolf"]
    assert [j["runs"] for j in wolf_jobs] == [10, 10, 5]


def test_invention_table(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    t = e.invention_table(11371)
    assert len(t["rows"]) == 9
    assert all(r["unit_cost"] > 0 for r in t["rows"])


def test_scan(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    prods = candidate_products(sde, e, DEFAULTS["scan"])
    assert 587 in prods and 11371 in prods
    assert {34, 20172, 16634} <= all_inputs(sde, prods)
    rows = score_industry(sde, e, prods, DEFAULTS["scan"])
    hist = {r["type_id"]: {"daily_volume": 100, "avg_price_7d": r["unit_sell_net"]} for r in rows}
    final = finalize_industry(rows, hist, DEFAULTS["scan"])
    assert final and final[0]["isk_per_day_realistic"] >= final[-1]["isk_per_day_realistic"]


def test_no_structure_fallback(sde):
    e = engine(sde, [])
    res = e.plan(587, 5)
    assert res["jobs"][0]["structure_virtual"]


def test_localized_names(sde):
    sde.lang = "fr"
    assert sde.name(11541) == "Propulseur à fusion"
    assert sde.name(36) == "Mexallon"            # pas de traduction -> anglais
    assert sde.name_en(11541) == "Fusion Thruster"
    hits = sde.search("propulseur")
    assert hits[0]["type_id"] == 11541 and hits[0]["alt"] == "Fusion Thruster"
    assert sde.search("fusion thr")[0]["type_id"] == 11541   # recherche aussi en anglais
    # les règles internes (catégorie de rig) restent basées sur l'anglais
    from app.industry import rig_category
    assert rig_category(sde, 11541, "manufacturing") == "advanced_components"
    sde.lang = "en"


def test_multi_target_plan(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    res = e.plan([(11371, 10), (587, 5)])
    assert res["summary"]["multi"] and len(res["targets"]) == 2
    rifter = [j for j in res["jobs"] if j["name"] == "Rifter"]
    # 10 Rifter pour les Wolf + 5 demandés = 15 runs
    assert sum(j["runs"] for j in rifter) == 15
    assert res["summary"]["revenue_net"] == pytest.approx(sum(t["revenue_net"] for t in res["targets"]))
    single = e.plan(11371, 10)
    assert single["summary"]["unit_cost"] is not None


def test_max_depth(sde):
    e = engine(sde, [NULL_RAITARU, NULL_TATARA])
    full = e.plan(11371, 10)
    assert full["full_depth"] == 3
    lvl1 = e.plan(11371, 10, max_depth=1)
    names = {j["name"] for j in lvl1["jobs"]}
    assert {"Wolf", "Rifter", "Fusion Thruster"} <= names and "Crystalline Carbonide" not in names
    assert any(b["name"] == "Crystalline Carbonide" for b in lvl1["buy"])
    lvl0 = e.plan(11371, 10, max_depth=0)
    assert {j["name"] for j in lvl0["jobs"]} == {"Wolf"}
    # un choix manuel « fabriquer » l'emporte sur la limite
    forced = e.plan(11371, 10, max_depth=1, overrides={16670: "build"})
    assert any(j["name"] == "Crystalline Carbonide" for j in forced["jobs"])
