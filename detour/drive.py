"""Simulate a car driving a route and emit GPS-like ticks (position + heading)."""
from __future__ import annotations

from dataclasses import dataclass

from .geo import bearing
from .world import Node, RoadNetwork


@dataclass(frozen=True)
class Tick:
    t: float          # seconds since start
    x: float          # meters east
    y: float          # meters north
    heading: float    # degrees clockwise from north
    speed: float      # m/s
    edge: tuple[Node, Node]  # street segment currently being driven


def simulate_drive(world: RoadNetwork, src: Node, dst: Node, dt: float = 1.0) -> list[Tick]:
    """Drive the fastest path src -> dst, sampling a tick every `dt` seconds."""
    path = world.shortest_path(src, dst)
    segs = []  # (t_start, t_end, a, b, speed)
    t = 0.0
    for a, b in zip(path, path[1:]):
        v = world.speed(a, b)
        dur = world.length(a, b) / v
        segs.append((t, t + dur, a, b, v))
        t += dur
    total = t

    ticks: list[Tick] = []
    k = 0
    now = 0.0
    while now <= total and segs:
        while now > segs[k][1] and k < len(segs) - 1:
            k += 1
        t0, t1, a, b, v = segs[k]
        frac = (now - t0) / (t1 - t0)
        ax, ay = world.xy(a)
        bx, by = world.xy(b)
        ticks.append(
            Tick(now, ax + (bx - ax) * frac, ay + (by - ay) * frac,
                 bearing(ax, ay, bx, by), v, (a, b))
        )
        now += dt
    return ticks
