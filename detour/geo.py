"""Small geometry helpers. Coordinates are meters: x = east, y = north.
Headings are degrees clockwise from north (0 = N, 90 = E)."""
import math


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def bearing(ax: float, ay: float, bx: float, by: float) -> float:
    """Compass bearing from A to B in [0, 360)."""
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360.0


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two headings, in [0, 180]."""
    d = abs(a - b) % 360.0
    return 360.0 - d if d > 180.0 else d
