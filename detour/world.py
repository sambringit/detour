"""Road networks. RoadNetwork is a general DIRECTED graph (one-way streets, curved
geometry, per-node U-turn rules); GridWorld is a synthetic city built on top of it;
osm.py builds one from real OpenStreetMap data.

Coordinates are meters (x = east, y = north). Nodes can be any hashable id."""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass
from typing import Hashable, Iterator

from . import native

Node = Hashable
CELL = 150.0  # spatial-index cell size in meters


@dataclass(frozen=True)
class POI:
    id: int
    name: str
    node: Node
    x: float
    y: float


class RoadNetwork:
    def __init__(self):
        self.pos: dict[Node, tuple[float, float]] = {}
        self.out: dict[Node, dict[Node, tuple[float, float]]] = {}  # a -> {b: (length m, speed m/s)}
        self.inn: dict[Node, list[Node]] = {}                        # b -> [a, ...]
        self.uturn_ok: dict[Node, bool] = {}  # may a car reverse here? (intersections, dead ends)
        self.pois: list[POI] = []
        self._times_cache: dict = {}
        self._ctg_cache: dict = {}
        self._index = None
        self.use_native = True   # set False to force the pure-Python cost_to_go on this network
        self._native = None      # lazy NativeGraph snapshot; False = this graph is unsupported

    # --- construction ---------------------------------------------------
    def add_node(self, node: Node, x: float, y: float, uturn_ok: bool = True) -> None:
        self.pos[node] = (x, y)
        self.out.setdefault(node, {})
        self.inn.setdefault(node, [])
        self.uturn_ok[node] = uturn_ok
        self._native = None

    def add_edge(self, a: Node, b: Node, length: float, speed: float) -> None:
        self.out[a][b] = (length, speed)
        self.inn[b].append(a)
        self._index = None
        self._native = None
        self._times_cache.clear()
        self._ctg_cache.clear()

    # --- basic accessors ------------------------------------------------
    @property
    def nodes(self) -> list[Node]:
        return list(self.pos)

    def xy(self, node: Node) -> tuple[float, float]:
        return self.pos[node]

    def length(self, a: Node, b: Node) -> float:
        return self.out[a][b][0]

    def speed(self, a: Node, b: Node) -> float:
        return self.out[a][b][1]

    def has_edge(self, a: Node, b: Node) -> bool:
        return b in self.out.get(a, {})

    def neighbors(self, node: Node) -> Iterator[tuple[Node, float]]:
        for nb, (length, speed) in self.out[node].items():
            yield nb, length / speed

    # --- spatial index --------------------------------------------------
    def _build_index(self) -> None:
        idx: dict = {}
        for a, nbrs in self.out.items():
            ax, ay = self.pos[a]
            for b in nbrs:
                bx, by = self.pos[b]
                for cx in range(math.floor(min(ax, bx) / CELL), math.floor(max(ax, bx) / CELL) + 1):
                    for cy in range(math.floor(min(ay, by) / CELL), math.floor(max(ay, by) / CELL) + 1):
                        idx.setdefault((cx, cy), []).append((a, b))
        self._index = idx

    def edge_candidates(self, x: float, y: float) -> list[tuple[Node, Node]]:
        """Directed edges near (x, y): at least everything within CELL meters."""
        if self._index is None:
            self._build_index()
        cx, cy = math.floor(x / CELL), math.floor(y / CELL)
        r = 1
        while True:
            seen: dict = {}
            for i in range(cx - r, cx + r + 1):
                for j in range(cy - r, cy + r + 1):
                    for e in self._index.get((i, j), ()):
                        seen[e] = None
            if seen or r > 60:
                return list(seen)
            r += 1

    # --- routing --------------------------------------------------------
    def shortest_path(self, src: Node, dst: Node) -> list[Node]:
        """Fastest path by travel time (Dijkstra)."""
        best = {src: 0.0}
        prev: dict[Node, Node] = {}
        heap = [(0.0, src)]
        while heap:
            cost, cur = heapq.heappop(heap)
            if cur == dst:
                break
            if cost > best.get(cur, float("inf")):
                continue
            for nb, w in self.neighbors(cur):
                c = cost + w
                if c < best.get(nb, float("inf")):
                    best[nb] = c
                    prev[nb] = cur
                    heapq.heappush(heap, (c, nb))
        path = [dst]
        while path[-1] != src:
            path.append(prev[path[-1]])
        return path[::-1]

    def travel_time(self, src: Node, dst: Node) -> float:
        path = self.shortest_path(src, dst)
        return sum(self.length(a, b) / self.speed(a, b) for a, b in zip(path, path[1:]))

    def times_to(self, target: Node) -> dict[Node, float]:
        """Fastest time (s) from every node TO `target`, following one-way rules and
        ignoring heading (a reversal is free). Cached."""
        cached = self._times_cache.get(target)
        if cached is not None:
            return cached
        best = {target: 0.0}
        heap = [(0.0, 0, target)]
        k = 0
        while heap:
            cost, _, cur = heapq.heappop(heap)
            if cost > best.get(cur, float("inf")):
                continue
            for u in self.inn[cur]:
                length, speed = self.out[u][cur]
                c = cost + length / speed
                if c < best.get(u, float("inf")):
                    best[u] = c
                    k += 1
                    heapq.heappush(heap, (c, k, u))
        self._times_cache[target] = best
        return best

    def native_graph(self):
        """The C++ snapshot of this network, or None when the native path is not in use
        (extension not built, numpy missing, use_native False, DETOUR_NATIVE=0, or a graph
        shape it does not model). Never raises."""
        if not (self.use_native and native.enabled()):
            return None
        if self._native is None:
            try:
                self._native = native.NativeGraph(self, cache=False)  # we cache below
            except native.UnsupportedGraph:
                self._native = False
        return self._native or None

    def cost_to_go(self, target: Node, uturn_penalty: float):
        """Direction-aware fastest time to `target`.

        Returns {(u, v): (seconds, route_has_uturn)} where (u, v) means "the car is at v
        and just arrived via the edge u->v". Reversing (v -> u) costs `uturn_penalty`
        extra seconds and is only allowed where uturn_ok[v] (intersections, dead ends).
        Backward Dijkstra over directed-edge states. Uses the optional C++ implementation
        when available (identical results, see tests/test_native_parity.py), otherwise the
        pure-Python one below. Cached per (target, uturn_penalty)."""
        key = (target, uturn_penalty)
        cached = self._ctg_cache.get(key)
        if cached is not None:
            return cached
        g = None
        if target in self.inn and native.finite(uturn_penalty):  # else Python raises/handles it
            ng = self.native_graph()
            if ng is not None:
                g = ng.cost_to_go(target, uturn_penalty)
        if g is None:
            g = self._cost_to_go_python(target, uturn_penalty)
        self._ctg_cache[key] = g
        return g

    def _cost_to_go_python(self, target: Node, uturn_penalty: float):
        """Reference pure-Python implementation (uncached). Kept as the fallback and as the
        oracle the native code is tested against."""
        g: dict = {}
        heap: list = []
        k = 0
        for u in self.inn[target]:
            g[(u, target)] = (0.0, False)
            heap.append((0.0, k, (u, target)))
            k += 1
        heapq.heapify(heap)
        while heap:
            cost, _, state = heapq.heappop(heap)
            cur_cost, cur_flag = g[state]
            if cost > cur_cost:
                continue
            m, w = state  # we have just traveled m -> w; its cost-to-go is `cost`
            step = self.length(m, w) / self.speed(m, w)
            for u in self.inn[m]:  # predecessor state (u, m): arrived at m via u -> m
                rev = u == w
                if rev and not self.uturn_ok[m]:
                    continue
                c = cost + step + (uturn_penalty if rev else 0.0)
                prev_state = (u, m)
                old = g.get(prev_state)
                if old is None or c < old[0]:
                    g[prev_state] = (c, cur_flag or rev)
                    k += 1
                    heapq.heappush(heap, (c, k, prev_state))
        return g

    def clear_caches(self) -> None:
        self._times_cache.clear()
        self._ctg_cache.clear()

    # --- points of interest ---------------------------------------------
    def add_pois(self, count: int, name: str = "Starbucks", seed: int = 0) -> None:
        rng = random.Random(seed)
        nodes = sorted(self.pos)
        start = len(self.pois)
        for i, node in enumerate(rng.sample(nodes, count)):
            x, y = self.xy(node)
            self.pois.append(POI(start + i, name, node, x, y))


class GridWorld(RoadNetwork):
    """Synthetic city: an n x n street grid with faster arterial roads."""

    DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

    def __init__(self, n: int = 30, block: float = 200.0, arterial_every: int = 5,
                 local_kmh: float = 30.0, arterial_kmh: float = 60.0):
        super().__init__()
        self.n = n
        self.block = block
        self.arterial_every = arterial_every
        self.local_ms = local_kmh / 3.6
        self.arterial_ms = arterial_kmh / 3.6
        for i in range(n):
            for j in range(n):
                self.add_node((i, j), i * block, j * block)
        for i in range(n):
            for j in range(n):
                for di, dj in self.DIRS:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < n and 0 <= nj < n:
                        self.add_edge((i, j), (ni, nj), block, self._grid_speed((i, j), (ni, nj)))

    def _grid_speed(self, a: Node, b: Node) -> float:
        if a[1] == b[1]:  # horizontal street, identified by its row
            arterial = a[1] % self.arterial_every == 0
        else:  # vertical street, identified by its column
            arterial = a[0] % self.arterial_every == 0
        return self.arterial_ms if arterial else self.local_ms

    def add_pois(self, count: int, name: str = "Starbucks", seed: int = 0) -> None:
        rng = random.Random(seed)
        taken = {p.node for p in self.pois}
        start_id = len(self.pois)
        while count > 0:
            node = (rng.randrange(self.n), rng.randrange(self.n))
            if node in taken:
                continue
            taken.add(node)
            x, y = self.xy(node)
            self.pois.append(POI(start_id, name, node, x, y))
            start_id += 1
            count -= 1
