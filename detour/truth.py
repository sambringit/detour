"""Ground truth: how long would it REALLY take the car to reach a POI right now?

Model: the car is mid-block on edge a->b and cannot turn around until it reaches
intersection b. From there it may continue or turn freely, but ANY reversal
(at b or at a later intersection) costs a fixed penalty in seconds, and is only
possible where the network allows it (never on a one-way street, never mid-curve).
This is the heading-aware cost a good suggestion should minimize. Distance alone,
and heading-blind routing, both ignore it."""
from __future__ import annotations

from .drive import Tick
from .geo import distance
from .world import POI, RoadNetwork

UTURN_PENALTY = 30.0  # seconds lost to turning around


def eta(world: RoadNetwork, tick: Tick, poi: POI, uturn_penalty: float = UTURN_PENALTY):
    """Return (seconds to reach poi, whether the best route contains a U-turn)."""
    a, b = tick.edge
    bx, by = world.xy(b)
    rem = distance(tick.x, tick.y, bx, by) / tick.speed  # time to reach b
    if poi.node == b:
        return rem, False
    state = world.cost_to_go(poi.node, uturn_penalty).get((a, b))
    if state is None:
        return float("inf"), False
    return rem + state[0], state[1]


def ground_truth(world: RoadNetwork, tick: Tick, uturn_penalty: float = UTURN_PENALTY):
    """Best POI by true ETA. Returns (poi, eta_seconds, has_uturn)."""
    best = None
    for p in world.pois:
        e, ut = eta(world, tick, p, uturn_penalty)
        if best is None or e < best[1]:
            best = (p, e, ut)
    return best
