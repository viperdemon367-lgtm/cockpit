"""Tests PvP : import EFT, compétences, temps d'entraînement, D-scan, conversions ESI."""
import math

import pytest

from app import fits as F
from app import pvp
from app.sde import SDE
from tests.fixture import make_zip, price_book_data

EFT = """[Wolf, Wolf brawl]
Damage Control II
[Empty Low slot]

200mm AutoCannon II, Hail S
200mm AutoCannon II, Hail S
200mm AutoCannon II, Hail S /offline

Small Projectile Burst Aerator I

Hobgoblin II x2

Hail S x1000
"""


@pytest.fixture
def sde():
    return SDE.from_zip_bytes(make_zip(), "test")


def test_dogma_loaded(sde):
    assert sde.slot[2889] == "high" and sde.slot[2048] == "low" and sde.slot[31718] == "rig"
    assert sde.req_skills[11371] == [(12095, 1), (3329, 5)]
    assert sde.skill_meta[12095] == (4, 168, 167)


def test_parse_eft(sde):
    [fit] = F.parse_eft(EFT, sde)
    assert fit["ship_type_id"] == 11371 and fit["name"] == "Wolf brawl" and not fit["unknown"]
    got = {(i["type_id"], i["slot"]): i["qty"] for i in fit["items"]}
    assert got[(2889, "high")] == 3
    assert got[(12608, "charge")] == 3       # munitions chargées
    assert got[(12608, "cargo")] == 1000     # soute
    assert got[(2456, "drone")] == 2
    assert got[(2048, "low")] == 1 and got[(31718, "rig")] == 1


def test_parse_eft_french_and_multi(sde):
    txt = "[Wolf, A]\nContrôle des dégâts II\nAutocanon 200 mm II\n\n[Rifter, B]\nDamage Control II\nTruc inconnu\n"
    fits = F.parse_eft(txt, sde)
    assert [f["name"] for f in fits] == ["A", "B"]
    assert fits[1]["unknown"] == ["Truc inconnu"]
    assert {i["type_id"] for i in fits[0]["items"]} == {2048, 2889}


def test_eft_roundtrip_and_esi(sde):
    [fit] = F.parse_eft(EFT, sde)
    again = F.parse_eft(F.to_eft(fit, sde), sde)[0]
    assert sorted((i["type_id"], i["slot"], i["qty"]) for i in again["items"] if i["slot"] != "charge") == \
        sorted((i["type_id"], i["slot"], i["qty"]) for i in fit["items"] if i["slot"] != "charge")
    esi = F.to_esi_fitting(fit, sde)
    flags = [i["flag"] for i in esi["items"]]
    assert flags.count("HiSlot0") == 1 and "HiSlot2" in flags and "LoSlot0" in flags and "RigSlot0" in flags
    assert {"type_id": 2456, "flag": "DroneBay", "quantity": 2} in esi["items"]
    back = F.from_esi_fitting({**esi, "ship_type_id": 11371}, sde)
    assert {(i["type_id"], i["slot"]) for i in back["items"]} >= {(2889, "high"), (2456, "drone"), (2048, "low")}


def test_sp_formula():
    # niveaux de référence d'une compétence de rang 1 : 250 / 1 415 / 8 000 / 45 255 / 256 000 SP
    assert [F.sp_for_level(1, l) for l in range(1, 6)] == [250, 1415, 8000, 45255, 256000]


def test_requirements_and_pilot_check(sde):
    [fit] = F.parse_eft(EFT, sde)
    need = F.requirements(F.fit_type_ids(fit), sde)
    # Wolf -> Assault Frigates I + Minmatar Frigate V ; canons T2 -> Small Projectile Turret V -> Gunnery I
    assert need == {12095: 1, 3329: 5, 3302: 5, 3300: 1}
    attrs = {"perception": 27, "willpower": 21, "memory": 20, "intelligence": 20, "charisma": 19}
    pilot = {"levels": {3329: 5, 3300: 5, 3302: 4}, "sp": {3302: F.sp_for_level(1, 4)}, "attrs": attrs, "queue": {}}
    r = F.check_pilot(need, pilot, sde)
    assert not r["can_fly"] and {m["skill_id"] for m in r["missing"]} == {12095, 3302}
    # Small Projectile Turret IV -> V : (256000 - 45255) SP à (27 + 21/2) SP/min
    spt = next(m for m in r["missing"] if m["skill_id"] == 3302)
    assert spt["time_s"] == pytest.approx((256000 - 45255) / (27 + 10.5) * 60)
    # Assault Frigates (rang 4, willpower/perception) 0 -> I
    af = next(m for m in r["missing"] if m["skill_id"] == 12095)
    assert af["time_s"] == pytest.approx(1000 / (21 + 13.5) * 60)
    plan = F.skill_plan_text(r["missing"], sde).splitlines()
    assert plan == ["Assault Frigates I", "Small Projectile Turret V"] or set(plan) == {"Assault Frigates I", "Small Projectile Turret V"}
    # une compétence déjà en file ne compte plus dans le temps restant
    pilot["queue"] = {3302: (5, "2026-11-01T10:00:00Z")}
    r2 = F.check_pilot(need, pilot, sde)
    assert r2["train_time_s"] == pytest.approx(af["time_s"])
    full = {"levels": {3329: 5, 3300: 5, 3302: 5, 12095: 1}, "sp": {}, "attrs": attrs, "queue": {}}
    assert F.check_pilot(need, full, sde)["can_fly"]


def test_skill_plan_prereq_order(sde):
    missing = [{"skill_id": 12095, "name_en": "Assault Frigates", "have": 0, "need": 2},
               {"skill_id": 3329, "name_en": "Minmatar Frigate", "have": 3, "need": 5}]
    assert F.skill_plan_text(missing, sde).splitlines() == [
        "Minmatar Frigate IV", "Minmatar Frigate V", "Assault Frigates I", "Assault Frigates II"]


def test_dscan(sde):
    _, adjusted, _ = price_book_data()
    text = "\n".join([
        "22456\tAlpha's Sabre\tSabre\t2,500 km",
        "22456\tBeta\tSabre\t-",
        "Scimitar de Bob\tScimitar\t1 234 km",
        "x\tMobile Small Warp Disruptor I\t12 km",
        "Rifter\tRifter\t15,3 UA",
        "Jita IV - Moon 4\tMoon\t2.3 AU",
    ])
    r = pvp.parse_dscan(text, sde, adjusted)
    by = {s["name"]: s for s in r["ships"]}
    assert by["Sabre"]["count"] == 2 and by["Sabre"]["on_grid"] == 1
    assert by["Scimitar"]["on_grid"] == 1 and by["Rifter"]["on_grid"] == 0
    labels = {t["label"] for t in r["threats"]}
    assert {"Bulles (interdicteur)", "Logistique (soins)", "Bulle posée"} <= labels
    assert r["total_ships"] == 4 and r["on_grid"] == 2 and r["has_distance"]
    assert r["estimated_value"] == 2 * 60_000_000 + 250_000_000 + 600_000 + 0


def test_distance_parsing():
    assert pvp._distance_km("2,500 km") == 2500
    assert pvp._distance_km("1 234 km") == 1234
    assert pvp._distance_km("12.5 km") == 12.5
    assert pvp._distance_km("850 m") == 0.85
    assert pvp._distance_km("-") is None
    assert pvp._distance_km("1,5 UA") > 1e8


def test_zkb_summary_and_threat():
    j = {"shipsDestroyed": 200, "shipsLost": 20, "iskDestroyed": 9e10, "iskLost": 1e10, "soloKills": 50,
         "dangerRatio": 85, "gangRatio": 60, "activepvp": {"kills": {"count": 12}},
         "topLists": [{"type": "shipType", "values": [{"shipTypeID": 22456, "shipName": "Sabre", "kills": 90}]}]}
    st = pvp.summarize_zkb(j)
    assert st["solo_pct"] == 25 and st["efficiency"] == 90 and st["top_ships"][0]["name"] == "Sabre"
    assert pvp.threat_level(st) == "très dangereux"
    assert pvp.threat_level(pvp.summarize_zkb({})) == "inconnu"


def test_standings_classification():
    st = pvp.merge_standings([
        {"personal": {111: 10.0}, "corp": {200: -10.0}, "alliance": {300: -5.0, 222: 5.0}},
        {"personal": {111: -5.0}},       # un autre perso a ce pilote en -5 : on garde le plus hostile
    ])
    assert st["personal"][111] == -5.0
    mine_c, mine_a = {99}, {500}
    assert pvp.classify(1, 99, None, st, mine_c, mine_a)[0] == "member"
    assert pvp.classify(111, 1, None, st, mine_c, mine_a)[0] == "bad"          # standing perso
    assert pvp.classify(2, 200, 300, st, mine_c, mine_a)[0] == "terrible"      # corpo cible plus précise que son alliance
    assert pvp.classify(3, 201, 300, st, mine_c, mine_a)[0] == "bad"           # via l'alliance
    assert pvp.classify(4, 222, None, st, mine_c, mine_a)[0] == "good"
    assert pvp.classify(5, 7, 8, st, mine_c, mine_a)[0] == "neutral"


XML = """<?xml version="1.0" ?>
<fittings>
  <fitting name="[Wolf] DPS">
    <description value="Doctrine brawl"/>
    <shipType value="Wolf"/>
    <hardware slot="low slot 0" type="Damage Control II"/>
    <hardware slot="hi slot 0" type="200mm AutoCannon II"/>
    <hardware slot="hi slot 1" type="200mm AutoCannon II"/>
    <hardware slot="rig slot 0" type="Small Projectile Burst Aerator I"/>
    <hardware qty="2" slot="drone bay" type="Hobgoblin II"/>
    <hardware qty="500" slot="cargo" type="Hail S"/>
  </fitting>
  <fitting name="[Wolf] Tackle">
    <description value=""/>
    <shipType value="Wolf"/>
    <hardware slot="low slot 0" type="Damage Control II"/>
  </fitting>
  <fitting name="Sabre - Bulle">
    <shipType value="Sabre"/>
    <hardware slot="low slot 0" type="Module Fantôme"/>
  </fitting>
</fittings>"""


def test_parse_xml(sde):
    fits = F.parse_xml(XML, sde)
    assert [f["name"] for f in fits] == ["[Wolf] DPS", "[Wolf] Tackle", "Sabre - Bulle"]
    got = {(i["type_id"], i["slot"]): i["qty"] for i in fits[0]["items"]}
    assert got == {(2048, "low"): 1, (2889, "high"): 2, (31718, "rig"): 1, (2456, "drone"): 2, (12608, "cargo"): 500}
    assert fits[0]["notes"] == "Doctrine brawl"
    assert fits[2]["unknown"] == ["Module Fantôme"]
    assert F.parse_any(XML, sde)[0] == "xml" and F.parse_any("[Wolf, x]\nDamage Control II", sde)[0] == "eft"


def test_xml_rejects_entities(sde):
    with pytest.raises(ValueError):
        F.parse_xml('<!DOCTYPE x [<!ENTITY a "b">]><fittings/>', sde)


def test_roles_and_prefix(sde):
    assert F.guess_role(sde, 11985) == "Logistique" and F.guess_role(sde, 22456) == "Tackle"
    assert F.guess_role(sde, 11371) == "DPS"
    assert F.guess_role(sde, 11371, "Wolf Logi armor") == "Logistique"
    assert F.guess_role(sde, 11985, "Scimitar") == "Logistique"
    assert F.split_prefix("[Vexor] DPS") == ("Vexor", "DPS")
    assert F.split_prefix("Vexor - Logi") == ("Vexor", "Logi")
    assert F.split_prefix("Vexor Navy Issue") == (None, "Vexor Navy Issue")
