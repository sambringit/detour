"""Load a real road network from an OpenStreetMap XML extract (.osm, .osm.bz2, .osm.gz).

Map data (c) OpenStreetMap contributors, ODbL.

What is modelled
  * drivable highway classes only (no footways / cycleways / parking aisles / private)
  * one-way streets (oneway=yes/1/true/-1, motorways, roundabouts) -> directed edges
  * speed from maxspeed (km/h or mph) else a default per road class
  * straight segments between OSM nodes (use an un-simplified extract, which is what
    Overpass/openstreetmap.org export give you)
  * only the largest strongly connected component is kept, so every node can reach
    every other node (no unreachable islands)
  * U-turns are allowed only at intersections and dead ends (nodes whose number of
    distinct neighbours is not 2), never mid-curve
  * optional real POIs: nodes whose tags match e.g. ("amenity", "fuel") are snapped
    to the nearest road node
"""
from __future__ import annotations

import bz2
import gzip
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .world import POI, RoadNetwork

DRIVABLE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service",
}
DEFAULT_KMH = {
    "motorway": 105, "trunk": 88, "primary": 72, "secondary": 64, "tertiary": 56,
    "unclassified": 48, "residential": 40, "living_street": 16, "service": 24,
}
ONEWAY_YES = {"yes", "true", "1"}


def _open(path: Path):
    s = str(path)
    if s.endswith(".bz2"):
        return bz2.open(path, "rb")
    if s.endswith(".gz"):
        return gzip.open(path, "rb")
    return open(path, "rb")


def parse_maxspeed(value: str | None) -> float | None:
    """'40' / '40 km/h' -> km/h; '25 mph' -> km/h; anything else -> None."""
    if not value:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh)?\s*$", value.lower())
    if not m:
        return None
    v = float(m.group(1))
    return v * 1.609344 if m.group(2) == "mph" else v


def way_speed_ms(tags: dict) -> float:
    hw = tags["highway"]
    kmh = parse_maxspeed(tags.get("maxspeed"))
    if kmh is None:
        kmh = DEFAULT_KMH[hw.removesuffix("_link")] * (0.6 if hw.endswith("_link") else 1.0)
    return max(kmh, 5.0) / 3.6


def way_direction(tags: dict) -> str:
    """'both', 'forward' or 'backward' relative to the way's node order."""
    ow = tags.get("oneway")
    if ow == "-1":
        return "backward"
    if ow in ONEWAY_YES:
        return "forward"
    if ow == "no":
        return "both"
    if tags.get("junction") == "roundabout" or tags["highway"] in ("motorway", "motorway_link"):
        return "forward"
    return "both"


def _is_drivable(tags: dict) -> bool:
    if tags.get("highway") not in DRIVABLE:
        return False
    if tags.get("area") == "yes":
        return False
    if tags.get("access") in ("no", "private"):
        return False
    if tags.get("highway") == "service" and tags.get("service") in ("parking_aisle", "driveway"):
        return False
    return True


def _largest_scc(nodes, out) -> set:
    """Kosaraju, iterative. Returns the node set of the largest strongly connected component."""
    order, seen = [], set()
    for s in nodes:
        if s in seen:
            continue
        seen.add(s)
        stack = [(s, iter(out[s]))]
        while stack:
            v, it = stack[-1]
            for w in it:
                if w not in seen:
                    seen.add(w)
                    stack.append((w, iter(out[w])))
                    break
            else:
                order.append(v)
                stack.pop()
    rev: dict = {n: [] for n in nodes}
    for a in nodes:
        for b in out[a]:
            rev[b].append(a)
    comp_best: set = set()
    assigned: set = set()
    for s in reversed(order):
        if s in assigned:
            continue
        comp, stack = {s}, [s]
        assigned.add(s)
        while stack:
            v = stack.pop()
            for w in rev[v]:
                if w not in assigned:
                    assigned.add(w)
                    comp.add(w)
                    stack.append(w)
        if len(comp) > len(comp_best):
            comp_best = comp
    return comp_best


def _tag_matches(value: str, want: str | None) -> bool:
    """want=None: any value; '~text': case-insensitive substring; otherwise exact match."""
    if want is None:
        return True
    if want.startswith("~"):
        return want[1:].lower() in value.lower()
    return value == want


def load_osm(path, poi_tag: tuple[str, str | None] | None = None, poi_name: str = "POI"):
    """Parse an OSM extract into a RoadNetwork. Returns (network, n_real_pois_found).

    poi_tag=("amenity", "fuel") puts every matching node into network.pois (snapped to the
    nearest road node). Use value None to match any value of the key, or "~text" for a
    case-insensitive substring match (e.g. ("name", "~starbucks"))."""
    path = Path(path)
    coords: dict[int, tuple[float, float]] = {}
    ways: list[tuple[list[int], dict]] = []
    poi_nodes: list[tuple[float, float]] = []
    with _open(path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.get("action") == "delete" or el.get("visible") == "false":
                el.clear()  # JOSM-deleted / invisible objects
                continue
            if el.tag == "node":
                lat, lon = float(el.get("lat")), float(el.get("lon"))
                coords[int(el.get("id"))] = (lat, lon)
                if poi_tag:
                    for t in el:
                        if t.tag == "tag" and t.get("k") == poi_tag[0] and _tag_matches(
                                t.get("v", ""), poi_tag[1]):
                            poi_nodes.append((lat, lon))
                            break
                el.clear()
            elif el.tag == "way":
                tags = {t.get("k"): t.get("v") for t in el if t.tag == "tag"}
                if _is_drivable(tags):
                    refs = [int(n.get("ref")) for n in el if n.tag == "nd"]
                    ways.append((refs, tags))
                el.clear()

    used = {r for refs, _ in ways for r in refs if r in coords}
    if not used:
        raise ValueError(f"no drivable roads found in {path}")
    lat0 = sum(coords[n][0] for n in used) / len(used)
    lon0 = sum(coords[n][1] for n in used) / len(used)
    kx = 111_320.0 * math.cos(math.radians(lat0))
    ky = 110_574.0

    def project(lat: float, lon: float) -> tuple[float, float]:
        return (lon - lon0) * kx, (lat - lat0) * ky

    # directed edge list with metric length and speed
    out: dict[int, dict[int, tuple[float, float]]] = {n: {} for n in used}
    for refs, tags in ways:
        v = way_speed_ms(tags)
        d = way_direction(tags)
        for a, b in zip(refs, refs[1:]):
            if a not in coords or b not in coords or a == b:
                continue
            (ax, ay), (bx, by) = project(*coords[a]), project(*coords[b])
            length = math.hypot(bx - ax, by - ay)
            if length < 0.5:
                continue
            if d in ("both", "forward"):
                out[a][b] = (length, v)
            if d in ("both", "backward"):
                out[b][a] = (length, v)

    keep = _largest_scc(sorted(used), out)
    net = RoadNetwork()
    nbrs: dict[int, set] = {n: set() for n in keep}
    for a in keep:
        for b in out[a]:
            if b in keep:
                nbrs[a].add(b)
                nbrs[b].add(a)
    for n in sorted(keep):
        x, y = project(*coords[n])
        net.add_node(n, x, y, uturn_ok=len(nbrs[n]) != 2)
    for a in sorted(keep):
        for b, (length, speed) in out[a].items():
            if b in keep:
                net.add_edge(a, b, length, speed)

    if poi_nodes:
        ids = sorted(keep)
        pts = [net.xy(n) for n in ids]
        seen_nodes = set()
        for lat, lon in poi_nodes:
            px, py = project(lat, lon)
            j = min(range(len(ids)), key=lambda i: (pts[i][0] - px) ** 2 + (pts[i][1] - py) ** 2)
            if ids[j] in seen_nodes:
                continue
            seen_nodes.add(ids[j])
            net.pois.append(POI(len(net.pois), poi_name, ids[j], *pts[j]))
    return net, len(net.pois)
