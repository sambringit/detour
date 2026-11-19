"""What a phone actually knows: a noisy GPS fix and compass heading.
Scorers see ONLY this, never the true road segment the car is on."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .drive import Tick


@dataclass(frozen=True)
class Obs:
    t: float
    x: float
    y: float
    heading: float  # degrees clockwise from north
    speed: float    # m/s


def observe(tick: Tick, rng: random.Random, pos_sigma: float = 8.0, head_sigma: float = 10.0) -> Obs:
    """Corrupt a true tick with Gaussian GPS position and heading noise."""
    return Obs(
        t=tick.t,
        x=tick.x + rng.gauss(0.0, pos_sigma),
        y=tick.y + rng.gauss(0.0, pos_sigma),
        heading=(tick.heading + rng.gauss(0.0, head_sigma)) % 360.0,
        speed=tick.speed,
    )
