import math

from detour.drive import simulate_drive
from detour.geo import angle_diff, bearing
from detour.world import GridWorld


def test_bearing_and_angle_diff():
    assert bearing(0, 0, 0, 10) == 0       # north
    assert bearing(0, 0, 10, 0) == 90      # east
    assert bearing(0, 0, 0, -10) == 180    # south
    assert angle_diff(350, 10) == 20
    assert angle_diff(0, 180) == 180


def test_arterial_is_faster():
    w = GridWorld(n=10, arterial_every=5)
    assert w.speed((0, 0), (1, 0)) > w.speed((0, 1), (1, 1))  # row 0 arterial, row 1 local


def test_shortest_path_prefers_arterial():
    w = GridWorld(n=11, arterial_every=5)
    path = w.shortest_path((0, 0), (10, 0))
    assert path == [(i, 0) for i in range(11)]  # straight along the arterial


def test_travel_time_symmetric():
    w = GridWorld(n=12)
    assert math.isclose(w.travel_time((1, 1), (9, 7)), w.travel_time((9, 7), (1, 1)))


def test_drive_ticks_end_at_destination_and_heading_valid():
    w = GridWorld(n=12)
    ticks = simulate_drive(w, (0, 0), (8, 5))
    x, y = w.xy((8, 5))
    assert math.hypot(ticks[-1].x - x, ticks[-1].y - y) < 20 * 1.0  # within 1 tick of arrival
    assert all(0 <= t.heading < 360 for t in ticks)
    assert ticks[0].t == 0


def test_pois_unique_and_seeded():
    a, b = GridWorld(n=20), GridWorld(n=20)
    a.add_pois(15, seed=7)
    b.add_pois(15, seed=7)
    assert [p.node for p in a.pois] == [p.node for p in b.pois]
    assert len({p.node for p in a.pois}) == 15
