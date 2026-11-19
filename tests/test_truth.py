import math

from detour.drive import Tick
from detour.scorers import NearestByDistance, NearestByDriveTimeFree
from detour.truth import UTURN_PENALTY, eta, ground_truth
from detour.world import POI, GridWorld

V = 60 / 3.6  # arterial speed, m/s


def _setup():
    """Car just past node (5,0) heading east on the row-0 arterial.
    A = Starbucks at (5,0): 10 m behind. B = Starbucks at (8,0): 590 m ahead."""
    w = GridWorld(n=11, arterial_every=5)
    A = POI(0, "S", (5, 0), 1000.0, 0.0)
    B = POI(1, "S", (8, 0), 1600.0, 0.0)
    w.pois = [A, B]
    tk = Tick(t=0, x=1010.0, y=0.0, heading=90.0, speed=V, edge=((5, 0), (6, 0)))
    return w, A, B, tk


def test_eta_ahead_has_no_uturn():
    w, A, B, tk = _setup()
    e, ut = eta(w, tk, B)
    assert not ut
    assert math.isclose(e, (190 + 400) / V, rel_tol=1e-9)


def test_eta_behind_pays_uturn_penalty():
    w, A, B, tk = _setup()
    e, ut = eta(w, tk, A)
    assert ut
    assert math.isclose(e, 190 / V + UTURN_PENALTY + 200 / V, rel_tol=1e-9)


def test_ground_truth_prefers_ahead_over_closer_behind():
    w, A, B, tk = _setup()
    poi, _, _ = ground_truth(w, tk)
    assert poi.id == B.id


def test_distance_baseline_picks_the_one_behind():
    w, A, B, tk = _setup()
    assert NearestByDistance().pick(w, tk).id == A.id


def test_heading_blind_drive_time_also_picks_behind():
    # Free reversal makes A (10 m back) look nearly instant: the flaw we want to fix.
    w, A, B, tk = _setup()
    assert NearestByDriveTimeFree().pick(w, tk).id == A.id


def test_regret_is_positive_for_baseline_pick():
    w, A, B, tk = _setup()
    best = ground_truth(w, tk)[1]
    assert eta(w, tk, A)[0] - best > 10  # ~18 s worse than the true best
