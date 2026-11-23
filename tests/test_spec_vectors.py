"""Checks the three test vectors in docs/algorithm.md against the implementation."""
import math

from detour.obs import Obs
from detour.scorers import HeadingAware, NearestByDistance
from detour.world import POI, RoadNetwork



def _street(uturn_at_2: bool = True) -> RoadNetwork:
    w = RoadNetwork()
    for i in range(4):
        w.add_node(i, 100.0 * i, 0.0, uturn_ok=(uturn_at_2 or i != 2))
    for i in range(3):
        w.add_edge(i, i + 1, 100.0, 10.0)
        w.add_edge(i + 1, i, 100.0, 10.0)
    w.pois = [POI(0, "A", 1, 100.0, 0.0), POI(1, "B", 3, 300.0, 0.0)]
    return w


def _ring() -> RoadNetwork:
    w = RoadNetwork()
    for n, (x, y) in {0: (0, 0), 1: (100, 0), 2: (100, 100), 3: (0, 100)}.items():
        w.add_node(n, float(x), float(y), uturn_ok=False)
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        w.add_edge(a, b, 100.0, 10.0)
    w.pois = [POI(0, "A", 0, 0.0, 0.0), POI(1, "B", 3, 0.0, 100.0), POI(2, "C", 2, 100.0, 100.0)]
    return w


def test_vector_a_behind_vs_ahead():
    w = _street()
    obs = Obs(0.0, 150.0, 0.0, 90.0, 10.0)
    assert NearestByDistance().pick(w, obs).name == "A"
    scorer = HeadingAware(uturn_penalty=20.0)
    scores = scorer.scores(w, obs)
    assert math.isclose(scores[0], 35.0) and math.isclose(scores[1], 15.0)
    assert scorer.pick(w, obs).name == "B"


def test_vector_b_loop_around_one_way_block():
    w = _ring()
    obs = Obs(0.0, 50.0, 0.0, 90.0, 10.0)
    assert NearestByDistance().pick(w, obs).name == "A"
    scorer = HeadingAware(uturn_penalty=20.0)
    scores = scorer.scores(w, obs)
    assert math.isclose(scores[0], 35.0)
    assert math.isclose(scores[1], 25.0)
    assert math.isclose(scores[2], 15.0)
    assert scorer.pick(w, obs).name == "C"


def test_vector_c_reversal_not_allowed_at_one_node():
    w = _street(uturn_at_2=False)
    obs = Obs(0.0, 150.0, 0.0, 90.0, 10.0)
    scores = HeadingAware(uturn_penalty=20.0).scores(w, obs)
    assert math.isclose(scores[0], 55.0)  # on to the dead end at node 3, reverse, come back
    assert math.isclose(scores[1], 15.0)
