"""Carte : sécurité, itinéraires, Thera, ponts de saut, systèmes proches."""
import pytest

from app import galaxy as GX
from app.sde import SDE
from tests.fixture import make_zip


@pytest.fixture
def sde():
    return SDE.from_zip_bytes(make_zip(), "t")


def ids(sde, *names):
    return [sde.find_system(n) for n in names]


def test_map_loaded(sde):
    assert len(sde.systems) == 9 and sde.regions[10000060] == "Delve"
    jita, per = ids(sde, "Jita", "Perimeter")
    assert per in sde.gates[jita] and jita in sde.gates[per]
    assert sde.systems[jita]["schematic"]


def test_security_display():
    assert GX.display_sec(0.9459) == 0.9 and GX.display_sec(0.45) == 0.5 and GX.display_sec(0.449) == 0.4
    assert GX.display_sec(0.02) == 0.1 and GX.display_sec(-0.385) == -0.4
    assert GX.sec_class(0.45) == "high" and GX.sec_class(0.3) == "low" and GX.sec_class(0.0) == "null"
    assert GX.sec_color(1.0) == "#2c75e1" and GX.sec_color(-0.5) == "#8d3264"


def test_routes(sde):
    g = GX.build_graph(sde)
    jita, ahb, tama, dq = ids(sde, "Jita", "Ahbazon", "Tama", "1DQ1-A")
    short = GX.route(g, sde, jita, ahb, "shortest")
    assert short == [jita, tama, ahb]                        # 2 sauts par Tama (low-sec)
    safe = GX.route(g, sde, jita, ahb, "secure")
    assert len(safe) == 4 and tama not in safe               # 3 sauts en high-sec
    assert GX.route(g, sde, jita, ahb, "shortest", avoid={tama}) == safe or len(GX.route(g, sde, jita, ahb, "shortest", avoid={tama})) == 4
    assert GX.route(g, sde, jita, sde.find_system("Isolé")) is None
    assert GX.route(g, sde, jita, dq)[-1] == dq


def test_bridges_and_thera(sde):
    jita, t5, per, dq = ids(sde, "Jita", "T5ZI-S", "Perimeter", "1DQ1-A")
    pairs, bad = GX.parse_jump_bridges("1DQ1-A » Jita\nT5ZI-S <-> Tama\nnimportequoi\n# commentaire", sde)
    assert pairs == [(dq, jita), (t5, sde.find_system("Tama"))] and bad == ["nimportequoi"]
    g = GX.build_graph(sde, pairs)
    assert GX.route(g, sde, jita, dq) == [jita, dq] and g[jita][dq] == "bridge"
    worms = GX.parse_evescout([{"out_system_id": 31000005, "out_system_name": "Thera", "in_system_id": per,
                                "in_system_name": "Perimeter", "max_ship_size": "large", "remaining_hours": 9},
                               {"out_system_id": 31000005, "in_system_id": t5}, {"bad": 1}])
    assert len(worms) == 2 and worms[0]["ship_size"] == "large"
    g2 = GX.build_graph(sde, (), [(w["system_id"], w["hub_id"]) for w in worms])
    assert GX.route(g2, sde, per, t5) == [per, GX.THERA, t5]


def test_nearby_and_links(sde):
    g = GX.build_graph(sde)
    near = GX.within_jumps(g, sde.find_system("1DQ1-A"), 2)
    assert {sde.systems[k]["name"] for k in near} == {"1DQ1-A", "T5ZI-S", "Ahbazon", "Urlen", "Tama"}
    assert GX.dotlan_system("1DQ1-A") == "https://evemaps.dotlan.net/system/1DQ1-A"
    assert GX.dotlan_region("The Forge", "Jita") == "https://evemaps.dotlan.net/map/The_Forge/Jita"
    assert GX.dotlan_route(["Jita", "Amarr"]) == "https://evemaps.dotlan.net/route/Jita:Amarr"


def test_ansiblex_names(sde):
    dq, t5, jita = ids(sde, "1DQ1-A", "T5ZI-S", "Jita")
    structs = [{"name": "1DQ1-A » T5ZI-S - Highway", "system_id": dq},
               {"name": "T5ZI-S » 1DQ1-A - Highway back", "system_id": t5},       # même pont dans l'autre sens
               {"name": "Jita » 1DQ1-A (Test)", "system_id": None},
               {"name": "Citadelle quelconque", "system_id": jita}]
    pairs = GX.ansiblex_pairs(structs, sde)
    assert pairs == [(dq, t5), (jita, dq)]
    assert GX.pairs_text(pairs, sde) == "1DQ1-A » T5ZI-S\nJita » 1DQ1-A"


def test_parse_sov_formats():
    from app.esi import parse_sov
    old = [{"system_id": 1, "alliance_id": 10, "corporation_id": 5}, {"system_id": 2, "faction_id": 500001}, {"system_id": 3}]
    assert parse_sov(old) == {"1": {"alliance_id": 10, "faction_id": None}, "2": {"alliance_id": None, "faction_id": 500001}}
    new = [{"solar_system_id": 4, "owner": {"alliance_id": 11}}, {"systemId": 5, "owner": {"id": 12, "type": "alliance"}},
           {"solar_system_id": 6, "owner": {"id": 500002, "type": "faction"}}]
    assert parse_sov(new) == {"4": {"alliance_id": 11, "faction_id": None}, "5": {"alliance_id": 12, "faction_id": None},
                              "6": {"alliance_id": None, "faction_id": 500002}}
