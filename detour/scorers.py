"""Candidate-ranking strategies. Each exposes `name`, `pick(world, obs) -> POI`
and optionally `reset()` (called at the start of every drive).

`obs` is a NOISY GPS observation (see obs.py); no scorer sees the true road segment.

  NearestByDistance        straight-line distance (the behaviour in the original story)
  NearestByDriveTimeFree   road-network drive time, but heading-blind: assumes the car
                           can leave the matched street via either end, i.e. reverse free
  HeadingAware             map-match WITH heading, then rank by direction-aware ETA
                           (every reversal costs a penalty), optionally with hysteresis
"""
from __future__ import annotations

from .geo import distance
from .matching import TrackMatcher, match
from .world import POI, RoadNetwork

INF = float("inf")


class NearestByDistance:
    name = "nearest_distance"

    def pick(self, world: RoadNetwork, obs) -> POI:
        return min(world.pois, key=lambda p: distance(obs.x, obs.y, p.x, p.y))


class NearestByDriveTimeFree:
    name = "nearest_drive_time"

    def pick(self, world: RoadNetwork, obs) -> POI:
        m = match(world, obs, use_heading=False)
        tb = (1.0 - m.t) * world.length(m.a, m.b) / world.speed(m.a, m.b)  # on to the end
        ta = (m.t * world.length(m.b, m.a) / world.speed(m.b, m.a)          # or straight back
              if world.has_edge(m.b, m.a) else INF)

        def cost(p: POI) -> float:
            tt = world.times_to(p.node)
            return min(ta + tt.get(m.a, INF), tb + tt.get(m.b, INF))

        return min(world.pois, key=cost)


class HeadingAware:
    """Rank POIs by the time to actually reach them given the direction of travel.

    uturn_penalty is the scorer's OWN belief about U-turn cost; the benchmark's ground
    truth uses a different value, so this scorer is deliberately mis-specified.
    margin > 0 turns on hysteresis: keep the current suggestion unless another one is
    at least `margin` seconds faster."""

    def __init__(self, uturn_penalty: float = 20.0, margin: float = 0.0, name: str | None = None,
                 tracked: bool = False):
        self.uturn_penalty = uturn_penalty
        self.margin = margin
        self.tracked = tracked  # use the track-aware matcher (needs a stream of fixes)
        self.name = name or ("heading_aware_hys" if margin > 0 else "heading_aware")
        self._current: int | None = None
        self._tracker: TrackMatcher | None = None

    def reset(self) -> None:
        self._current = None
        self._tracker = None

    def _match(self, world: RoadNetwork, obs):
        if not self.tracked:
            return match(world, obs)
        if self._tracker is None or self._tracker.world is not world:
            self._tracker = TrackMatcher(world)
        return self._tracker.update(obs)

    def scores(self, world: RoadNetwork, obs) -> dict[int, float]:
        m = self._match(world, obs)
        rem = (1.0 - m.t) * world.length(m.a, m.b) / world.speed(m.a, m.b)
        out = {}
        for p in world.pois:
            if p.node == m.b:
                out[p.id] = rem
            else:
                state = world.cost_to_go(p.node, self.uturn_penalty).get((m.a, m.b))
                out[p.id] = rem + state[0] if state else INF
        return out

    def pick(self, world: RoadNetwork, obs) -> POI:
        sc = self.scores(world, obs)
        best_id = min(sc, key=sc.get)
        if (self._current is not None and self._current in sc
                and sc[self._current] - sc[best_id] < self.margin):
            best_id = self._current
        self._current = best_id
        return next(p for p in world.pois if p.id == best_id)
