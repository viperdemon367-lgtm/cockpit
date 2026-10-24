"""Mini SDE au format JSON Lines de CCP, pour tester le moteur hors ligne."""
import io
import json
import zipfile

CATEGORIES = [(4, "Material"), (6, "Ship"), (9, "Blueprint"), (16, "Skill"), (17, "Commodity"), (35, "Decryptors"),
              (24, "Reaction"), (7, "Module"), (8, "Charge"), (18, "Drone"), (22, "Deployable")]
GROUPS = [(18, "Mineral", 4), (25, "Frigate", 6), (324, "Assault Frigate", 6), (105, "Frigate Blueprint", 9),
          (334, "Construction Components", 17), (429, "Composite", 4), (427, "Moon Materials", 4),
          (333, "Datacores", 17), (270, "Science", 16), (1304, "Decryptors", 35), (1888, "Composite Reaction Formulas", 24),
          (447, "Construction Component Blueprints", 9),
          (257, "Spaceship Command", 16), (255, "Gunnery", 16), (55, "Projectile Weapon", 7), (60, "Damage Control", 7),
          (373, "Advanced Autocannon Ammo", 8), (100, "Combat Drone", 18), (781, "Rig Projectile Weapon", 7),
          (541, "Interdictor", 6), (832, "Logistics", 6), (12, "Mobile Warp Disruptor", 22)]
TYPES = [
    (34, "Tritanium", 18, 101, None, 0.01), (35, "Pyerite", 18, 101, None, 0.01), (36, "Mexallon", 18, 101, None, 0.01),
    (587, "Rifter", 25, 61, 1, 27289), (691, "Rifter Blueprint", 105, 260, None, 0.01),
    (11371, "Wolf", 324, 400, 2, 28100), (11372, "Wolf Blueprint", 105, None, None, 0.01),
    (11541, "Fusion Thruster", 334, 802, None, 1), (99001, "Fusion Thruster Blueprint", 447, 800, None, 0.01),
    (16670, "Crystalline Carbonide", 429, 500, None, 0.01), (99002, "Crystalline Carbonide Reaction Formula", 1888, 1849, None, 0.01),
    (16634, "Atmospheric Gases", 427, 501, None, 0.05), (16643, "Cadmium", 427, 501, None, 0.05),
    (20172, "Datacore - Mechanical Engineering", 333, 1880, None, 0.1),
    (20416, "Datacore - Minmatar Starship Engineering", 333, 1880, None, 0.1),
    (3392, "Mechanical Engineering", 270, 375, None, 0.01), (11445, "Minmatar Starship Engineering", 270, 375, None, 0.01),
    (21791, "Minmatar Encryption Methods", 270, 375, None, 0.01),
    (34201, "Accelerant Decryptor", 1304, 1873, None, 0.1),
    (3329, "Minmatar Frigate", 257, 377, None, 0.01), (12095, "Assault Frigates", 257, 377, None, 0.01),
    (3300, "Gunnery", 255, 364, None, 0.01), (3302, "Small Projectile Turret", 255, 364, None, 0.01),
    (2889, "200mm AutoCannon II", 55, 576, 2, 5), (2048, "Damage Control II", 60, 615, 2, 5),
    (12608, "Hail S", 373, 991, 2, 0.0025), (2456, "Hobgoblin II", 100, 837, 2, 5),
    (31718, "Small Projectile Burst Aerator I", 781, 1219, 1, 5),
    (22456, "Sabre", 541, 826, 2, 43000), (11985, "Scimitar", 832, 438, 2, 85000),
    (12198, "Mobile Small Warp Disruptor I", 12, 405, 1, 65),
]
DOGMA = {
    11371: {"attrs": {182: 12095, 277: 1, 183: 3329, 278: 5}},
    12095: {"attrs": {275: 4, 180: 168, 181: 167, 182: 3329, 277: 5}},
    3329: {"attrs": {275: 2, 180: 167, 181: 168}},
    3300: {"attrs": {275: 1, 180: 167, 181: 168}},
    3302: {"attrs": {275: 1, 180: 167, 181: 168, 182: 3300, 277: 1}},
    2889: {"attrs": {182: 3302, 277: 5}, "effects": [12]},
    2048: {"effects": [11]},
    31718: {"effects": [2663]},
}
FR_EXTRA = {2889: "Autocanon 200 mm II", 2048: "Contrôle des dégâts II"}
BLUEPRINTS = [
    {"_key": 691, "blueprintTypeID": 691, "maxProductionLimit": 300, "activities": {
        "manufacturing": {"time": 6000, "materials": [{"typeID": 34, "quantity": 30000}, {"typeID": 35, "quantity": 6000},
                                                      {"typeID": 36, "quantity": 2500}],
                          "products": [{"typeID": 587, "quantity": 1}]},
        "copying": {"time": 4800},
        "invention": {"time": 63900, "materials": [{"typeID": 20172, "quantity": 2}, {"typeID": 20416, "quantity": 2}],
                      "products": [{"typeID": 11372, "quantity": 10, "probability": 0.34}],
                      "skills": [{"typeID": 3392, "level": 1}, {"typeID": 11445, "level": 1}, {"typeID": 21791, "level": 1}]}}},
    {"_key": 11372, "blueprintTypeID": 11372, "maxProductionLimit": 10, "activities": {
        "manufacturing": {"time": 18000, "materials": [{"typeID": 587, "quantity": 1}, {"typeID": 11541, "quantity": 15},
                                                       {"typeID": 34, "quantity": 5000}],
                          "products": [{"typeID": 11371, "quantity": 1}]}}},
    {"_key": 99001, "blueprintTypeID": 99001, "maxProductionLimit": 1000, "activities": {
        "manufacturing": {"time": 300, "materials": [{"typeID": 16670, "quantity": 20}],
                          "products": [{"typeID": 11541, "quantity": 1}]}}},
    {"_key": 99002, "blueprintTypeID": 99002, "maxProductionLimit": 1000, "activities": {
        "reaction": {"time": 10800, "materials": [{"typeID": 16634, "quantity": 100}, {"typeID": 16643, "quantity": 100}],
                     "products": [{"typeID": 16670, "quantity": 10000}]}}},
]

FR_NAMES = {11541: "Propulseur à fusion", 34: "Tritanium", 587: "Rifter"}

FR_NAMES.update(FR_EXTRA)

PRICES = {34: 4, 35: 10, 36: 60, 587: 600_000, 11371: 30_000_000, 11541: 30_000, 16670: 60, 16634: 50, 16643: 300,
          20172: 80_000, 20416: 120_000, 34201: 1_200_000, 2889: 900_000, 2048: 700_000, 12608: 200,
          2456: 1_000_000, 31718: 600_000, 22456: 60_000_000, 11985: 250_000_000}


MAP_REGIONS = [(10000002, "The Forge"), (10000060, "Delve"), (10000033, "The Citadel")]
MAP_CONST = [(20000020, "Kimotoro"), (20000700, "XPJ1-6"), (20000400, "Ihilakken")]
# id, nom, région, constellation, sécurité, x, z
MAP_SYSTEMS = [
    (30000142, "Jita", 10000002, 20000020, 0.9459, 0, 0),
    (30000144, "Perimeter", 10000002, 20000020, 0.9065, 10, 2),
    (30000139, "Urlen", 10000002, 20000020, 0.6, 20, 4),
    (30002813, "Tama", 10000033, 20000400, 0.3, 12, -6),
    (30005196, "Ahbazon", 10000033, 20000400, 0.4, 25, -5),
    (30004759, "1DQ1-A", 10000060, 20000700, -0.385, 40, -10),
    (30004807, "T5ZI-S", 10000060, 20000700, -0.29, 50, -12),
    (30000145, "Sobaseki", 10000002, 20000020, 0.5, 5, 6),
    (30000146, "Isolé", 10000002, 20000020, 0.7, 99, 99),
]
MAP_GATES = [("Jita", "Perimeter"), ("Perimeter", "Urlen"), ("Urlen", "Ahbazon"), ("Ahbazon", "1DQ1-A"),
             ("1DQ1-A", "T5ZI-S"), ("Jita", "Sobaseki"), ("Sobaseki", "Urlen"), ("Jita", "Tama"), ("Tama", "Ahbazon")]


PI_TYPES = [  # id, nom, groupe, catégorie
    (11, "Planet (Temperate)", 7, 2), (2016, "Planet (Barren)", 7, 2), (13, "Planet (Gas)", 7, 2),
    (2268, "Aqueous Liquids", 1032, 42), (2267, "Base Metals", 1032, 42), (2288, "Carbon Compounds", 1032, 42),
    (2073, "Micro Organisms", 1032, 42), (2270, "Noble Metals", 1032, 42), (2305, "Autotrophs", 1032, 42),
    (2287, "Complex Organisms", 1032, 42), (2310, "Noble Gas", 1032, 42), (2311, "Reactive Gas", 1032, 42),
    (2309, "Ionic Solutions", 1032, 42),
    (3645, "Water", 1042, 43), (2396, "Biofuels", 1042, 43), (2399, "Precious Metals", 1042, 43), (2398, "Reactive Metals", 1042, 43),
    (2329, "Biocells", 1034, 43), (9842, "Miniature Electronics", 1034, 43),
    (2344, "Condensates", 1040, 43), (2867, "Broadcast Node", 1041, 43),
]
PI_SCHEMATICS = [  # id, sortie, qté sortie, [(entrée, qté)], cycle
    (121, 3645, 20, [(2268, 3000)], 1800), (134, 2396, 20, [(2288, 3000)], 1800),
    (127, 2399, 20, [(2270, 3000)], 1800), (126, 2398, 20, [(2267, 3000)], 1800),
    (70, 2329, 5, [(2396, 40), (2399, 40)], 3600), (73, 9842, 5, [(2398, 40), (3645, 40)], 3600),
    (90, 2344, 3, [(2329, 10), (9842, 10)], 3600), (110, 2867, 1, [(2344, 6), (2329, 6), (3645, 40)], 3600),
]
PI_PLANETS = {"Jita": [(11, 1), (2016, 2), (13, 3)], "Perimeter": [(2016, 1)], "Urlen": [(11, 1), (11, 2)],
              "1DQ1-A": [(13, 1), (2016, 4)]}


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("categories.jsonl", "\n".join(json.dumps({"_key": k, "name": {"en": n}}) for k, n in CATEGORIES))
        z.writestr("groups.jsonl", "\n".join(json.dumps({"_key": k, "name": {"en": n, "fr": n}, "categoryID": c})
                                             for k, n, c in GROUPS))
        z.writestr("types.jsonl", "\n".join([json.dumps({"_key": k, "name": {"en": n}, "groupID": g, "published": True, "volume": 1})
                                              for k, n, g, _c in PI_TYPES] + [json.dumps({"_key": k, "name": {"en": n, **({"fr": FR_NAMES[k]} if k in FR_NAMES else {})},
                                                         "groupID": g, "published": True,
                                                         "marketGroupID": mg, "metaGroupID": meta, "volume": v})
                                            for k, n, g, mg, meta, v in TYPES]))
        z.writestr("blueprints.jsonl", "\n".join(json.dumps(b) for b in BLUEPRINTS))
        z.writestr("mapRegions.jsonl", "\n".join(json.dumps({"_key": k, "name": {"en": n}}) for k, n in MAP_REGIONS))
        z.writestr("mapConstellations.jsonl", "\n".join(json.dumps({"_key": k, "name": {"en": n}}) for k, n in MAP_CONST))
        z.writestr("mapSolarSystems.jsonl", "\n".join(json.dumps({
            "_key": k, "name": {"en": n}, "regionID": r, "constellationID": c, "securityStatus": sec,
            "position": {"x": x * 1e16, "y": 0, "z": zz * 1e16}, "position2D": {"x": x * 1e16, "y": zz * 1e16}})
            for k, n, r, c, sec, x, zz in MAP_SYSTEMS))
        ids = {n: k for k, n, *_ in MAP_SYSTEMS}
        gates, gid = [], 50000000
        for a, b in MAP_GATES:
            gates.append({"_key": gid, "solarSystemID": ids[a], "destination": {"solarSystemID": ids[b], "stargateID": gid + 1}})
            gates.append({"_key": gid + 1, "solarSystemID": ids[b], "destination": {"solarSystemID": ids[a], "stargateID": gid}})
            gid += 2
        z.writestr("mapStargates.jsonl", "\n".join(json.dumps(g) for g in gates))
        z.writestr("mapPlanets.jsonl", "\n".join(json.dumps({"_key": 40000000 + i * 10 + j, "solarSystemID": ids[n],
                                                                  "typeID": t, "celestialIndex": idx})
                                                      for i, (n, pls) in enumerate(PI_PLANETS.items()) for j, (t, idx) in enumerate(pls)))
        z.writestr("planetSchematics.jsonl", "\n".join(json.dumps({"_key": k, "cycleTime": c, "name": {"en": f"S{k}"}, "pins": [2469],
            "types": [{"_key": o, "isInput": False, "quantity": oq}] + [{"_key": i, "isInput": True, "quantity": q} for i, q in ins]})
            for k, o, oq, ins, c in PI_SCHEMATICS))
        z.writestr("typeDogma.jsonl", "\n".join(json.dumps({
            "_key": t, "dogmaAttributes": [{"attributeID": a, "value": v} for a, v in d.get("attrs", {}).items()],
            "dogmaEffects": [{"effectID": e, "isDefault": False} for e in d.get("effects", [])]}) for t, d in DOGMA.items()))
    return buf.getvalue()


def price_book_data():
    prices = {t: {"sell": p, "buy": p * 0.9, "sell_vol": 1e6, "buy_vol": 1e6} for t, p in PRICES.items()}
    adjusted = {t: {"adj": p, "avg": p} for t, p in PRICES.items()}
    indices = {30000142: {"manufacturing": 0.05, "invention": 0.06, "copying": 0.04, "reaction": 0.03},
               30004759: {"manufacturing": 0.02, "invention": 0.03, "copying": 0.02, "reaction": 0.02}}
    return prices, adjusted, indices
