"""Planétaire : tiers P0-P4, ressources par type de planète, analyse d'une zone, meilleurs systèmes."""
import pytest

from app.planetary import PI, planet_kind
from app.sde import SDE
from tests.fixture import make_zip


@pytest.fixture
def pi():
    return PI(SDE.from_zip_bytes(make_zip(), "t"))


def test_parse_and_tiers(pi):
    sde = pi.sde
    assert len(sde.pi_schematics) == 8 and sde.pi_producer[2867] == 110
    assert planet_kind(sde, 11) == "Temperate" and planet_kind(sde, 13) == "Gas"
    assert [pi.tier(t) for t in (2268, 3645, 2329, 2344, 2867)] == [0, 1, 2, 3, 4]
    assert {sde.name(x) for x in pi.p0_needed(2867)} == {"Carbon Compounds", "Noble Metals", "Base Metals", "Aqueous Liquids"}


def test_tree_quantities(pi):
    t = pi.tree(2867, 1)                       # 1 Broadcast Node
    cond = next(c for c in t["children"] if c["type_id"] == 2344)
    assert cond["qty"] == 6 and cond["tier"] == 3
    biocells = next(c for c in cond["children"] if c["type_id"] == 2329)
    assert biocells["qty"] == 20               # 6 Condensates x 10/3
    leaf = biocells["children"][0]["children"][0]
    assert leaf["tier"] == 0 and "Barren" in leaf["planets"]


def test_area_and_best_systems(pi):
    sde = pi.sde
    jita = sde.find_system("Jita")
    res = pi.analyze(jita, 1, {2867: {"sell": 1_000_000}, 2344: {"sell": 10_000}, 2329: {"sell": 1000}})
    names = {sde.systems[s["system_id"]]["name"] for s in res["systems"]}
    assert names == {"Jita", "Perimeter"}                       # Urlen est à 2 sauts
    assert res["kinds"]["Barren"] == 2 and res["kinds"]["Temperate"] == 1
    node = next(p for p in res["products"] if p["type_id"] == 2867)
    assert node["feasible"] and node["solo_systems"] == 2         # Jita et Perimeter : une planète stérile suffit
    assert node["margin_hour"] == pytest.approx((1_000_000 - 6 * 10_000 - 6 * 1000) * 1)   # par cycle d'1 h
    best = pi.best_systems(2867, jita, 2)
    assert best[0]["name"] == "Jita" and best[0]["coverage"] == best[0]["needed"] == 4
    planets = pi.system_planets(jita)
    assert planets[0]["name"] == "Jita I" and planets[0]["kind"] == "Temperate"
