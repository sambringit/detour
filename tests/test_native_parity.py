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

pytestmark = pytest.mark.skipif(not native.available, reason="C++ extension not built")

from detour.drive import simulate_drive  # noqa: E402
from detour.obs import observe  # noqa: E402
from detour.osm import load_osm  # noqa: E402
from detour.scorers import HeadingAware  # noqa: E402
from detour.world import POI, GridWorld, RoadNetwork  # noqa: E402
from tests.test_spec_vectors import _ring, _street  # noqa: E402

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
            r = compare(world.cost_to_go(t, pen), g.cost_to_go(t, pen))
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


def test_real_extract_ranking_parity(real_net):
    """Identical Obs streams -> identical HeadingAware scores and picks, Python vs native."""
    name, net = real_net
    net.pois = [POI(i, p.name, p.node, p.x, p.y) for i, p in enumerate(net.pois[:30])]
    g = native.NativeGraph(net)
    native_ctg = g.cost_to_go
    py_ctg = net.cost_to_go
    rng = random.Random(11)
    nodes = sorted(net.pos)
    compared = 0
    for _ in range(3):
        src, dst = rng.choice(nodes), rng.choice(nodes)
        ticks = simulate_drive(net, src, dst, dt=5.0)[:25]  # cap: map matching is the slow part
        obs_stream = [observe(tk, rng) for tk in ticks]  # one stream, used by both scorers
        for pen in PENALTIES:
            py_scorer, nat_scorer = HeadingAware(pen), HeadingAware(pen)
            for obs in obs_stream:
                s_py = py_scorer.scores(net, obs)
                pick_py = py_scorer.pick(net, obs).id
                net.cost_to_go = native_ctg  # scorer calls world.cost_to_go: swap in native
                try:
                    s_nat = nat_scorer.scores(net, obs)
                    pick_nat = nat_scorer.pick(net, obs).id
                finally:
                    net.cost_to_go = py_ctg
                assert s_py.keys() == s_nat.keys()
                for pid in s_py:
                    assert math.isclose(s_py[pid], s_nat[pid], rel_tol=REL_TOL) or s_py[pid] == s_nat[pid]
                assert pick_py == pick_nat, f"{name}: ranking pick differs"
                compared += 1
    assert compared > 0


def test_ranking_parity_on_grid_world():
    w = GridWorld(n=30)
    w.add_pois(12, seed=3)
    g = native.NativeGraph(w)
    rng = random.Random(5)
    for _ in range(4):
        src, dst = rng.choice(sorted(w.pos)), rng.choice(sorted(w.pos))
        if src == dst:
            continue
        for obs in [observe(tk, rng) for tk in simulate_drive(w, src, dst, dt=4.0)[:30]]:
            for pen in PENALTIES:
                a = HeadingAware(pen)
                s_py, pick_py = a.scores(w, obs), a.pick(w, obs).id
                orig = w.cost_to_go
                w.cost_to_go = g.cost_to_go
                try:
                    s_nat, pick_nat = a.scores(w, obs), a.pick(w, obs).id
                finally:
                    w.cost_to_go = orig
                assert pick_py == pick_nat
                assert all(math.isclose(s_py[k], s_nat[k], rel_tol=REL_TOL) or s_py[k] == s_nat[k] for k in s_py)
