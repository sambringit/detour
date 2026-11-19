"""Grade scorers against ground truth over simulated drives.

Per sampled tick we ask "if the driver searched right now, what would this scorer
suggest?" -- using a NOISY GPS observation -- and compare with the truly fastest POI
(ground truth uses the exact road position). Metrics:
  regret_s   extra seconds vs the best POI (mean, p90)
  optimal    share of ticks where the pick is (tied for) the best
  uturn      share of ticks where the pick's best route contains a U-turn
  flips_pm   how often the suggestion changes, per minute of driving"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .drive import Tick
from .geo import angle_diff, bearing, distance
from .matching import TrackMatcher, match
from .obs import observe
from .truth import UTURN_PENALTY, eta, ground_truth
from .world import GridWorld


@dataclass
class Stats:
    ticks: int = 0
    regret_sum: float = 0.0
    optimal: int = 0
    uturn: int = 0
    avoidable: int = 0  # pick needs a U-turn although the truly best stop does not
    flips: int = 0
    minutes: float = 0.0
    regrets: list[float] = field(default_factory=list)

    def merge(self, other: "Stats") -> None:
        self.ticks += other.ticks
        self.regret_sum += other.regret_sum
        self.optimal += other.optimal
        self.uturn += other.uturn
        self.avoidable += other.avoidable
        self.flips += other.flips
        self.minutes += other.minutes
        self.regrets += other.regrets

    def summary(self) -> dict:
        r = sorted(self.regrets)
        p90 = r[int(0.9 * (len(r) - 1))] if r else 0.0
        return {
            "ticks": self.ticks,
            "mean_regret_s": self.regret_sum / self.ticks,
            "p90_regret_s": p90,
            "optimal_pct": 100 * self.optimal / self.ticks,
            "uturn_pct": 100 * self.uturn / self.ticks,
            "avoidable_uturn_pct": 100 * self.avoidable / self.ticks,
            "flips_per_min": self.flips / self.minutes if self.minutes else 0.0,
        }


def _near(world, m, tk) -> bool:
    """Is the match 'good enough'? Within 25 m of the true position and travelling the
    same way (within 45 deg) -- a fairer test than exact segment equality when OSM
    streets are chopped into 15 m pieces."""
    ax, ay = world.xy(m.a)
    bx, by = world.xy(m.b)
    px, py = ax + (bx - ax) * m.t, ay + (by - ay) * m.t
    return distance(px, py, tk.x, tk.y) <= 25.0 and angle_diff(bearing(ax, ay, bx, by), tk.heading) < 45.0


def evaluate_drive(world: GridWorld, ticks: list[Tick], scorers, rng: random.Random,
                   stride: int = 3, pos_sigma: float = 8.0, head_sigma: float = 10.0,
                   truth_penalty: float = UTURN_PENALTY):
    """Return ({scorer.name: Stats}, match_counts) where match_counts has n, single_exact,
    single_near, track_exact, track_near (map-matching diagnostics, see _near).

    pos_sigma/head_sigma are the TRUE GPS noise levels. Scorers and the matcher keep
    their own fixed beliefs (8 m / 10 deg): the app does not know the noise exactly."""
    out = {s.name: Stats() for s in scorers}
    out["oracle"] = Stats()  # the ground truth itself: the best any scorer could do
    prev_pick = {s.name: None for s in scorers}
    prev_oracle = None
    for s in scorers:
        if hasattr(s, "reset"):
            s.reset()
    sampled = ticks[::stride]
    counts = {"n": 0, "single_exact": 0, "single_near": 0, "track_exact": 0, "track_near": 0}
    tracker = TrackMatcher(world)
    for tk in sampled:
        ob = observe(tk, rng, pos_sigma, head_sigma)  # one noisy fix shared by all scorers
        m, mt = match(world, ob), tracker.update(ob)
        counts["n"] += 1
        counts["single_exact"] += (m.a, m.b) == tk.edge
        counts["single_near"] += _near(world, m, tk)
        counts["track_exact"] += (mt.a, mt.b) == tk.edge
        counts["track_near"] += _near(world, mt, tk)
        best_poi, best_eta, best_ut = ground_truth(world, tk, truth_penalty)
        orc = out["oracle"]
        orc.ticks += 1
        orc.regrets.append(0.0)
        orc.optimal += 1
        orc.uturn += best_ut
        if prev_oracle is not None and best_poi.id != prev_oracle:
            orc.flips += 1
        prev_oracle = best_poi.id
        for s in scorers:
            st = out[s.name]
            poi = s.pick(world, ob)
            e, ut = eta(world, tk, poi, truth_penalty)  # judged from the TRUE position
            regret = e - best_eta
            st.ticks += 1
            st.regret_sum += regret
            st.regrets.append(regret)
            st.optimal += regret < 1e-6
            st.uturn += ut
            st.avoidable += ut and not best_ut
            if prev_pick[s.name] is not None and poi.id != prev_pick[s.name]:
                st.flips += 1
            prev_pick[s.name] = poi.id
    minutes = (sampled[-1].t - sampled[0].t) / 60 if len(sampled) > 1 else 0.0
    for st in out.values():
        st.minutes = minutes
    return out, counts
