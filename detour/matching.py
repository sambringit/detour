"""Map matching: snap a noisy GPS fix to a directed street segment.

Each candidate directed segment is scored by a Gaussian-style cost:
    (distance to segment / pos_sigma)^2 + (heading mismatch / head_sigma)^2
and the cheapest wins. With use_heading=False the heading term is dropped, which
is what a heading-blind system effectively does (direction is then arbitrary)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import angle_diff, bearing
from .world import Node, RoadNetwork


@dataclass(frozen=True)
class Match:
    a: Node     # segment start (the intersection the car came from)
    b: Node     # segment end (the intersection the car is heading to)
    t: float    # fraction of the way from a to b, in [0, 1]
    cost: float


def match(world: RoadNetwork, obs, pos_sigma: float = 8.0, head_sigma: float = 10.0,
          use_heading: bool = True, allowed: set | None = None) -> Match | None:
    """Best directed segment for one fix. `allowed` restricts the candidates (used by
    TrackMatcher); returns None if no allowed segment is near the fix."""
    best: Match | None = None
    for a, b in world.edge_candidates(obs.x, obs.y):
        if allowed is not None and (a, b) not in allowed:
            continue
        ax, ay = world.xy(a)
        bx, by = world.xy(b)
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 == 0.0:
            continue
        t = max(0.0, min(1.0, ((obs.x - ax) * dx + (obs.y - ay) * dy) / l2))
        d = math.hypot(obs.x - (ax + t * dx), obs.y - (ay + t * dy))
        cost = (d / pos_sigma) ** 2
        if use_heading:
            cost += (angle_diff(obs.heading, bearing(ax, ay, bx, by)) / head_sigma) ** 2
        if best is None or cost < best.cost:
            best = Match(a, b, t, cost)
    return best


def reachable_edges(world: RoadNetwork, prev: Match, horizon: float, behind: float = 40.0) -> set:
    """Directed segments the car could be on now, given where it was: the segment it was
    on, everything reachable ahead within `horizon` meters (no reversals), and a little
    behind it to absorb GPS jitter."""
    a, b = prev.a, prev.b
    out = {(a, b)}
    frontier = [(b, a, (1.0 - prev.t) * world.length(a, b))]
    while frontier:
        node, came_from, d = frontier.pop()
        if d > horizon:
            continue
        for w in world.out[node]:
            if w == came_from:
                continue
            out.add((node, w))
            frontier.append((w, node, d + world.length(node, w)))
    back = [(a, b, prev.t * world.length(a, b))]
    while back:
        node, came_to, d = back.pop()
        if d > behind:
            continue
        for u in world.inn[node]:
            if u == came_to:
                continue
            out.add((u, node))
            back.append((u, node, d + world.length(u, node)))
    return out


class TrackMatcher:
    """Stateful matcher: uses the previous match to restrict where the car can be now.
    Falls back to single-fix matching on the first fix or when it loses the track."""

    def __init__(self, world: RoadNetwork, pos_sigma: float = 8.0, head_sigma: float = 10.0,
                 margin: float = 40.0, lost_cost: float = 30.0):
        self.world, self.pos_sigma, self.head_sigma = world, pos_sigma, head_sigma
        self.margin, self.lost_cost = margin, lost_cost
        self.reset()

    def reset(self) -> None:
        self.prev: Match | None = None
        self.prev_t: float = 0.0

    def update(self, obs) -> Match:
        m = None
        if self.prev is not None:
            horizon = obs.speed * max(obs.t - self.prev_t, 0.0) + self.margin
            allowed = reachable_edges(self.world, self.prev, horizon)
            m = match(self.world, obs, self.pos_sigma, self.head_sigma, allowed=allowed)
            if m is not None and m.cost > self.lost_cost:
                m = None
        if m is None:
            m = match(self.world, obs, self.pos_sigma, self.head_sigma)
        self.prev, self.prev_t = m, obs.t
        return m
