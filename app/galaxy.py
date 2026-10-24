"""Carte de New Eden : sécurité, itinéraires, systèmes proches, ponts de saut, connexions Thera/Turnur, liens Dotlan."""
from __future__ import annotations

import heapq
import re
import urllib.parse
from collections import deque

THERA = 31000005
SEC_COLORS = {10: "#2c75e1", 9: "#399aeb", 8: "#4ecef8", 7: "#60dba3", 6: "#71e554", 5: "#f3fd82",
              4: "#dc6d07", 3: "#ce440f", 2: "#bb1116", 1: "#722020", 0: "#8d3264"}


def display_sec(sec: float) -> float:
    """Sécurité affichée en jeu : arrondie au dixième, mais un 0,0x positif s'affiche 0,1."""
    if 0 < sec < 0.05:
        return 0.1
    return round(sec + 1e-9, 1) if sec > 0 else round(sec, 1)


def sec_class(sec: float) -> str:
    d = display_sec(sec)
    return "high" if d >= 0.5 else ("low" if d > 0 else "null")


def sec_color(sec: float) -> str:
    d = display_sec(sec)
    return SEC_COLORS[0] if d <= 0 else SEC_COLORS[max(1, min(10, int(round(d * 10))))]


# ---------------------------------------------------------------------- liens externes
def _slug(name: str) -> str:
    return urllib.parse.quote(name.replace(" ", "_"))


def dotlan_system(name):
    return f"https://evemaps.dotlan.net/system/{_slug(name)}"


def dotlan_region(region, system=None):
    return f"https://evemaps.dotlan.net/map/{_slug(region)}" + (f"/{_slug(system)}" if system else "")


def dotlan_route(names):
    return "https://evemaps.dotlan.net/route/" + ":".join(_slug(n) for n in names)


def zkill_system(sid):
    return f"https://zkillboard.com/system/{sid}/"


# ---------------------------------------------------------------------- ponts de saut (Ansiblex)
def parse_jump_bridges(text: str, sde) -> tuple[list[tuple[int, int]], list[str]]:
    """Une ligne par pont : deux noms de systèmes séparés par » <-> --> - ou des espaces.
    Les formats courants (liste d'alliance, export Dotlan, « 1DQ1-A » T5ZI-S ») sont acceptés."""
    names = {s["name"].lower(): sid for sid, s in sde.systems.items()}
    pairs, bad = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        found = []
        for tok in re.split(r"[\s»«<>↔→←|,;]+|-->|<->|<-->", line):
            t = tok.strip(" -@:").lower()
            if t in names and names[t] not in found:
                found.append(names[t])
        if len(found) >= 2:
            a, b = found[0], found[1]
            if (a, b) not in pairs and (b, a) not in pairs:
                pairs.append((a, b))
        else:
            bad.append(line)
    return pairs, bad


def ansiblex_pairs(structures, sde) -> list[tuple[int, int]]:
    """Structures Ansiblex lues en jeu -> paires de systèmes. Nom : « 1DQ1-A » T5ZI-S - Nom du pont »."""
    names = {s["name"].lower(): sid for sid, s in sde.systems.items()}
    pairs = []
    for st in structures:
        name = st.get("name") or ""
        if "»" not in name:
            continue
        left, right = name.split("»", 1)
        dest = re.split(r"\s+-\s+|\s*\(", right.strip(), maxsplit=1)[0].strip().lower()
        a = st.get("system_id") or names.get(left.strip().lower())
        b = names.get(dest)
        if a and b and a != b and (a, b) not in pairs and (b, a) not in pairs:
            pairs.append((a, b))
    return pairs


def pairs_text(pairs, sde) -> str:
    return "\n".join(f"{sde.systems[a]['name']} » {sde.systems[b]['name']}" for a, b in pairs
                     if a in sde.systems and b in sde.systems)


# ---------------------------------------------------------------------- graphe et itinéraires
def build_graph(sde, jump_bridges=(), wormholes=()):
    """Graphe d'adjacence : portes + ponts de saut + trous de ver (Thera/Turnur). {système: {voisin: type}}"""
    g = {sid: {n: "gate" for n in sde.gates.get(sid, ())} for sid in sde.systems}
    for a, b in jump_bridges:
        if a in g and b in g:
            g[a].setdefault(b, "bridge")
            g[b].setdefault(a, "bridge")
    for a, b in wormholes:
        for x in (a, b):
            g.setdefault(x, {})
        g[a].setdefault(b, "wormhole")
        g[b].setdefault(a, "wormhole")
    return g


def route(graph, sde, start, end, mode="shortest", avoid=()):
    """Dijkstra. mode : shortest (moins de sauts), secure (évite low/null), insecure (évite le high)."""
    avoid = set(avoid) - {start, end}
    if start not in graph or end not in graph:
        return None

    def cost(sid):
        if sid not in sde.systems:          # Thera (espace W) : neutre
            return 1.0
        cls = sec_class(sde.systems[sid]["sec"])
        if mode == "secure":
            return 1.0 if cls == "high" else 1000.0
        if mode == "insecure":
            return 1000.0 if cls == "high" else 1.0
        return 1.0

    dist, prev = {start: 0.0}, {}
    heap = [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == end:
            break
        if d > dist.get(u, 1e18):
            continue
        for v in graph.get(u, {}):
            if v in avoid:
                continue
            nd = d + cost(v)
            if nd < dist.get(v, 1e18):
                dist[v], prev[v] = nd, u
                heapq.heappush(heap, (nd, v))
    if end not in dist:
        return None
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def within_jumps(graph, start, jumps, gates_only=False):
    """Systèmes à moins de N sauts : {système: distance}."""
    seen = {start: 0}
    q = deque([start])
    while q:
        u = q.popleft()
        if seen[u] >= jumps:
            continue
        for v, kind in graph.get(u, {}).items():
            if gates_only and kind != "gate":
                continue
            if v not in seen:
                seen[v] = seen[u] + 1
                q.append(v)
    return seen


# ---------------------------------------------------------------------- EVE-Scout (Thera / Turnur)
def parse_evescout(rows) -> list[dict]:
    """Normalise la réponse de https://api.eve-scout.com/v2/public/signatures."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        hub_id = r.get("out_system_id") or r.get("outSystemId")
        hub = r.get("out_system_name") or r.get("outSystemName") or ""
        sys_id = r.get("in_system_id") or r.get("inSystemId")
        if not hub_id or not sys_id:
            continue
        out.append({"hub_id": int(hub_id), "hub": hub, "system_id": int(sys_id),
                    "system": r.get("in_system_name") or r.get("inSystemName") or "",
                    "region": r.get("in_region_name") or r.get("inRegionName") or "",
                    "ship_size": r.get("max_ship_size") or r.get("maxShipSize") or "",
                    "remaining_hours": r.get("remaining_hours") or r.get("remainingHours"),
                    "expires_at": r.get("expires_at") or r.get("expiresAt"),
                    "signature": r.get("in_signature") or r.get("out_signature") or ""})
    return out
