"""Parity tests: the optional C++ cost_to_go must reproduce the pure-Python one.

Skipped automatically when the extension (or numpy) is not available, so CI jobs without
a compiler still pass. Seconds are compared with rel_tol 1e-9 (in practice they are
bit-identical); the has_uturn flag and the reachable-state sets are compared and reported
SEPARATELY, so a tie-breaking difference can never hide behind a seconds match."""
import math
import random
from pathlib import Path

import pytest

from detour import native

pytestmark = pytest.mark.skipif(not native.enabled(), reason="C++ extension not built (or DETOUR_NATIVE=0)")

from detour.drive import simulate_drive  # noqa: E402
from detour.obs import observe  # noqa: E402
from detour.osm import load_osm  # noqa: E402
from detour.scorers import HeadingAware  # noqa: E402
from detour.world import POI, GridWorld, RoadNetwork  # noqa: E402
from test_spec_vectors import _ring, _street  # noqa: E402  (sibling test module; works under plain `pytest`)

DATA = Path(__file__).resolve().parent.parent / "data"
PENALTIES = (20.0, 30.0)  # scorer belief, ground truth (truth.UTURN_PENALTY)
REL_TOL = 1e-9


def compare(py: dict, nat: dict) -> dict:
    """Mismatch report for one cost_to_go call, one list per kind of mismatch."""
    shared = py.keys() & nat.keys()
    return {
        "missing_in_native": sorted(py.keys() - nat.keys(), key=repr),
        "extra_in_native": sorted(nat.keys() - py.keys(), key=repr),
        "seconds": [k for k in shared if not math.isclose(py[k][0], nat[k][0], rel_tol=REL_TOL)],
        "flag": [k for k in shared if py[k][1] != nat[k][1]],
        "states": len(shared),
    }


def check_world(world: RoadNetwork, targets, penalties=PENALTIES) -> int:
    g = native.NativeGraph(world)
    total = 0
    for t in targets:
        for pen in penalties:
            r = compare(world._cost_to_go_python(t, pen), g.cost_to_go(t, pen))
            ctx = f"target={t!r} penalty={pen}"
            # reachability and seconds first, flag mismatches reported on their own
            assert not r["missing_in_native"] and not r["extra_in_native"], f"reachable states differ: {ctx}"
            assert not r["seconds"], f"seconds mismatch ({len(r['seconds'])} states): {ctx}"
            assert not r["flag"], f"has_uturn flag mismatch only ({len(r['flag'])} states): {ctx}"
            total += r["states"]
    return total


# --- (a) the three vectors in docs/algorithm.md ----------------------------------------
@pytest.mark.parametrize("make", [_street, lambda: _street(False), _ring], ids=["A", "C", "B"])
def test_spec_vector_graphs(make):
    w = make()
    assert check_world(w, list(w.pos), penalties=(20.0,)) > 0


def test_vector_values_native():
    g = native.NativeGraph(_street())
    d = g.cost_to_go(1, 20.0)  # place A at node 1
    # state (1, 2) = just arrived at node 2 from node 1; back to node 1 = 20 s reversal + 10 s
    assert math.isclose(d[(1, 2)][0], 30.0) and d[(1, 2)][1] is True
    g3 = native.NativeGraph(_street(uturn_at_2=False))
    assert math.isclose(g3.cost_to_go(1, 20.0)[(1, 2)][0], 50.0)  # on to node 3, reverse, back


def test_unreachable_states_are_omitted():
    w = RoadNetwork()  # one-way chain 0 -> 1 -> 2: nothing can reach node 0
    for i in range(3):
        w.add_node(i, 100.0 * i, 0.0)
    w.add_edge(0, 1, 100.0, 10.0)
    w.add_edge(1, 2, 100.0, 10.0)
    for t in range(3):
        check_world(w, [t])
    assert native.NativeGraph(w).cost_to_go(0, 20.0) == {}
    cost, _ = native.NativeGraph(w).cost_to_go_arrays(1, 20.0)
    assert math.isinf(cost[1]) and cost[0] == 0.0  # edge (1, 2) cannot reach node 1


def test_parallel_edges_are_refused_so_caller_can_fall_back():
    w = RoadNetwork()
    for i in range(2):
        w.add_node(i, 100.0 * i, 0.0)
    w.add_edge(0, 1, 100.0, 10.0)
    w.add_edge(0, 1, 120.0, 10.0)  # overwrites out[0][1] but appends 0 to inn[1] again
    with pytest.raises(native.UnsupportedGraph):
        native.NativeGraph(w)


# --- (b) synthetic grid -------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_gridworld_30(seed):
    w = GridWorld(n=30)
    targets = random.Random(seed).sample(sorted(w.pos), 25)
    assert check_world(w, targets) > 0


@pytest.mark.parametrize("seed", [0, 1])
def test_gridworld_tie_stress(seed):
    """Penalties 0, 12 and 24 s equal zero or one grid edge, so reversal routes tie exactly
    with non-reversal routes and the has_uturn flag depends on which one settles first.
    With the default penalties (20, 30) such ties almost never happen, so the tests above
    cannot see a tie-breaking bug; this one can (verified by breaking the C++ on purpose:
    '<=' instead of '<', or reversed predecessor order, give thousands of flag mismatches
    while seconds stay identical)."""
    w = GridWorld(n=30)
    targets = random.Random(seed).sample(sorted(w.pos), 20)
    assert check_world(w, targets, penalties=(0.0, 12.0, 24.0)) > 0


# --- (c) real extracts ----------------------------------------------------------------------
EXTRACTS = {
    "west_oakland": "west_oakland/West-Oakland.osm.bz2",
    "san_francisco": "san_francisco/sfsubset.osm.bz2",
    "helsinki": "helsinki/Helsinki.osm.bz2",
}


@pytest.fixture(scope="module", params=list(EXTRACTS))
def real_net(request):
    net, _ = load_osm(str(DATA / EXTRACTS[request.param]), poi_tag=("amenity", "cafe"), poi_name="Cafe")
    if len(net.pois) < 8:  # sparse extract: add deterministic POIs so ranking has candidates
        net.pois = []
        net.add_pois(8, seed=0)
    return request.param, net


def test_real_extract_cost_to_go(real_net):
    name, net = real_net
    nodes = sorted(net.pos)
    targets = nodes if len(nodes) <= 100 else random.Random(7).sample(nodes, 20)
    targets = list(dict.fromkeys(targets + [p.node for p in net.pois[:5]]))
    assert check_world(net, targets) > 0


def _stream_results(net, penalty, obs_stream, native_on):
    """HeadingAware scores + picks for one Obs stream with the native path on or off."""
    net.use_native = native_on
    net.clear_caches()  # drop cached cost_to_go so this run recomputes with the chosen path
    if native_on:
        assert net.native_graph() is not None, "native path should be active"
    else:
        assert net.native_graph() is None
    scorer = HeadingAware(penalty)
    out = [(scorer.scores(net, obs), scorer.pick(net, obs).id) for obs in obs_stream]
    net.use_native = True
    return out


def _assert_same_rankings(py, nat, label):
    assert len(py) == len(nat) > 0
    for (s_py, pick_py), (s_nat, pick_nat) in zip(py, nat):
        assert s_py.keys() == s_nat.keys()
        for pid in s_py:
            assert s_py[pid] == s_nat[pid] or math.isclose(s_py[pid], s_nat[pid], rel_tol=REL_TOL)
        assert pick_py == pick_nat, f"{label}: ranking pick differs"


def test_real_extract_ranking_parity(real_net):
    """Identical Obs streams -> identical HeadingAware scores and picks, Python vs native."""
    name, net = real_net
    net.pois = [POI(i, p.name, p.node, p.x, p.y) for i, p in enumerate(net.pois[:30])]
    rng = random.Random(11)
    nodes = sorted(net.pos)
    for _ in range(3):
        src, dst = rng.choice(nodes), rng.choice(nodes)
        ticks = simulate_drive(net, src, dst, dt=5.0)[:25]  # cap: map matching is the slow part
        obs_stream = [observe(tk, rng) for tk in ticks]  # one stream, used by both runs
        for pen in PENALTIES:
            _assert_same_rankings(_stream_results(net, pen, obs_stream, False),
                                  _stream_results(net, pen, obs_stream, True), name)


def test_ranking_parity_on_grid_world():
    w = GridWorld(n=30)
    w.add_pois(12, seed=3)
    rng = random.Random(5)
    nodes = sorted(w.pos)
    for _ in range(4):
        src, dst = rng.choice(nodes), rng.choice(nodes)
        if src == dst:
            continue
        obs_stream = [observe(tk, rng) for tk in simulate_drive(w, src, dst, dt=4.0)[:30]]
        for pen in PENALTIES:
            _assert_same_rankings(_stream_results(w, pen, obs_stream, False),
                                  _stream_results(w, pen, obs_stream, True), "grid")


# --- the wiring in RoadNetwork itself ---------------------------------------------------------
def test_roadnetwork_uses_native_and_returns_same_type_as_python():
    w = GridWorld(n=8)
    assert w.native_graph() is not None
    got = w.cost_to_go((3, 3), 20.0)
    assert got is w.cost_to_go((3, 3), 20.0)  # cached per (target, penalty), same object
    ref = w._cost_to_go_python((3, 3), 20.0)
    assert got == ref  # exact equality: same keys, same floats, same bools
    k = next(iter(got))
    assert type(got[k][0]) is float and type(got[k][1]) is bool


def test_use_native_false_and_env_switch_fall_back(monkeypatch):
    w = GridWorld(n=6)
    w.use_native = False
    assert w.native_graph() is None
    assert w.cost_to_go((2, 2), 20.0) == w._cost_to_go_python((2, 2), 20.0)
    w2 = GridWorld(n=6)
    monkeypatch.setenv("DETOUR_NATIVE", "0")
    assert not native.enabled() and w2.native_graph() is None
    monkeypatch.setenv("DETOUR_NATIVE", "1")
    assert native.enabled() and w2.native_graph() is not None


def test_adding_edges_or_nodes_invalidates_the_snapshot():
    w = _street()
    before = w.cost_to_go(3, 20.0)
    assert w.native_graph() is not None
    w.add_node(4, 400.0, 0.0)
    w.add_edge(3, 4, 100.0, 10.0)
    w.add_edge(4, 3, 100.0, 10.0)
    assert w._native is None and not w._ctg_cache  # snapshot and cache both dropped
    after = w.cost_to_go(4, 20.0)
    assert after == w._cost_to_go_python(4, 20.0) and (3, 4) in after
    assert (3, 4) not in before and (3, 4) in w.cost_to_go(3, 20.0)  # new edge is visible


def test_unsupported_graphs_fall_back_to_python():
    w = RoadNetwork()
    for i in range(3):
        w.add_node(i, 100.0 * i, 0.0)
    w.add_edge(0, 1, 100.0, 10.0)
    w.add_edge(1, 0, 100.0, 10.0)
    w.add_edge(1, 2, 100.0, 0.0)  # zero speed: Python only fails if this edge is ever relaxed
    assert w.native_graph() is None
    assert w._native is False  # remembered, not retried on every call
    assert w.cost_to_go(0, 20.0) == w._cost_to_go_python(0, 20.0)


def test_unknown_target_and_nonfinite_penalty_keep_python_behaviour():
    w = GridWorld(n=4)
    with pytest.raises(KeyError):
        w.cost_to_go("nope", 20.0)
    inf = float("inf")
    assert w.cost_to_go((1, 1), inf) == w._cost_to_go_python((1, 1), inf)
