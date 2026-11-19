import random

from detour.drive import Tick, simulate_drive
from detour.matching import match
from detour.obs import Obs, observe
from detour.scorers import HeadingAware, NearestByDistance
from detour.world import POI, GridWorld

V = 60 / 3.6


def _scenario():
    w = GridWorld(n=11, arterial_every=5)
    A = POI(0, "S", (5, 0), 1000.0, 0.0)   # 10 m behind the car
    B = POI(1, "S", (8, 0), 1600.0, 0.0)   # 590 m ahead
    w.pois = [A, B]
    ob = Obs(t=0, x=1010.0, y=0.0, heading=90.0, speed=V)  # east on row-0 arterial
    return w, A, B, ob


def test_observe_zero_noise_is_identity():
    tk = Tick(5.0, 123.0, 456.0, 270.0, V, ((1, 1), (0, 1)))
    ob = observe(tk, random.Random(0), 0.0, 0.0)
    assert (ob.x, ob.y, ob.heading) == (123.0, 456.0, 270.0)


def test_match_uses_heading_to_pick_direction():
    w, _, _, ob = _scenario()
    east = match(w, ob)
    assert (east.a, east.b) == ((5, 0), (6, 0))
    west = match(w, Obs(0, 1010.0, 0.0, 270.0, V))
    assert (west.a, west.b) == ((6, 0), (5, 0))


def test_match_recovers_true_edge_on_noiseless_drive():
    w = GridWorld(n=15)
    ticks = simulate_drive(w, (1, 1), (12, 9))
    hits = sum((m := match(w, t)).a == t.edge[0] and m.b == t.edge[1] for t in ticks)
    assert hits / len(ticks) > 0.95  # only intersection ticks can be ambiguous


def test_heading_aware_beats_nearest_in_scenario():
    w, A, B, ob = _scenario()
    assert NearestByDistance().pick(w, ob).id == A.id
    assert HeadingAware().pick(w, ob).id == B.id


def test_hysteresis_keeps_current_unless_margin_beaten():
    w, A, B, ob = _scenario()
    # Seed the scorer so its current suggestion is A (the worse choice).
    s = HeadingAware(margin=100.0)
    s._current = A.id
    assert s.pick(w, ob).id == A.id           # B is only ~12 s better: below the 100 s margin
    s2 = HeadingAware(margin=5.0)
    s2._current = A.id
    assert s2.pick(w, ob).id == B.id          # 12 s > 5 s margin: switches


def test_reset_clears_state():
    w, A, B, ob = _scenario()
    s = HeadingAware(margin=100.0)
    s.pick(w, ob)
    s.reset()
    assert s._current is None
