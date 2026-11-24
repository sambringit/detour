"""Optional native (C++) cost_to_go. Importing this module never fails: if the compiled
extension `detour._ctg` is missing, `available` is False and nothing here is used.

NativeGraph snapshots a RoadNetwork into dense arrays. Edge ids follow inn[] order
(for each node b in pos order, for each a in inn[b]) so predecessor iteration in C++
is the same order as in the Python code."""
from __future__ import annotations

try:
    import numpy as np

    from . import _ctg
except ImportError:  # no numpy or extension not built: pure-Python path is used
    np = None
    _ctg = None

available = _ctg is not None


class UnsupportedGraph(ValueError):
    """The network has a shape the native path does not model (caller falls back to Python)."""


class NativeGraph:
    def __init__(self, net):
        if not available:
            raise ImportError("detour._ctg is not built")
        self.node_index = {n: i for i, n in enumerate(net.pos)}
        edge_from, edge_to, edge_time, in_off = [], [], [], [0]
        self.edge_key = []  # edge id -> (u, v) node labels
        for b in net.pos:
            preds = net.inn[b]
            if len(set(preds)) != len(preds):
                raise UnsupportedGraph(f"parallel edges into node {b!r}")
            for a in preds:
                length, speed = net.out[a][b]
                edge_from.append(self.node_index[a])
                edge_to.append(self.node_index[b])
                edge_time.append(length / speed)  # same expression as Python: bit-identical
                self.edge_key.append((a, b))
            in_off.append(len(edge_from))
        if len(edge_from) != sum(len(v) for v in net.out.values()):
            raise UnsupportedGraph("out/inn adjacency disagree")
        self.edge_from = np.asarray(edge_from, dtype=np.int32)
        self.edge_to = np.asarray(edge_to, dtype=np.int32)
        self.edge_time = np.asarray(edge_time, dtype=np.float64)
        self.in_off = np.asarray(in_off, dtype=np.int64)
        self.in_edges = np.arange(len(edge_from), dtype=np.int32)  # ids already in inn order
        self.uturn_ok = np.asarray([net.uturn_ok[n] for n in net.pos], dtype=np.uint8)
        self.edge_id = {k: i for i, k in enumerate(self.edge_key)}
        self._cache: dict = {}  # (target, penalty) -> dict; a NativeGraph is a snapshot, so
                                # the owner drops it (and this cache) when edges change

    def cost_to_go_arrays(self, target, uturn_penalty: float):
        """(seconds float64, has_uturn uint8) per edge id; inf seconds = unreachable."""
        return _ctg.cost_to_go(self.edge_from, self.edge_to, self.edge_time, self.in_off,
                               self.in_edges, self.uturn_ok, self.node_index[target],
                               float(uturn_penalty))

    def cost_to_go(self, target, uturn_penalty: float) -> dict:
        """Same return type as RoadNetwork.cost_to_go: {(u, v): (seconds, has_uturn)}. Cached."""
        key = (target, uturn_penalty)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        cost, flag = self.cost_to_go_arrays(target, uturn_penalty)
        ids = np.flatnonzero(np.isfinite(cost)).tolist()
        sec = cost[ids].tolist()
        fl = flag[ids].astype(bool).tolist()
        ek = self.edge_key
        out = {ek[i]: (s, f) for i, s, f in zip(ids, sec, fl)}
        self._cache[key] = out
        return out
