"""Tiny stats helpers (no scipy needed)."""
from __future__ import annotations

import math

# two-sided 95% Student-t critical values by degrees of freedom
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def mean_ci(values: list[float]) -> tuple[float, float]:
    """Return (mean, 95% CI half-width) across independent seeds."""
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))
    return m, _T95.get(n - 1, 1.96) * sd / math.sqrt(n)
