import math

from detour import experiment
from detour.stats import mean_ci


def test_mean_ci_basic():
    m, c = mean_ci([1.0, 3.0])
    assert m == 2.0
    assert math.isclose(c, 12.706 * math.sqrt(2) / math.sqrt(2))  # sd=sqrt(2), n=2
    assert mean_ci([5.0]) == (5.0, 0.0)


def test_experiment_is_deterministic_and_ranks_scorers():
    specs = [("dist",), ("ha", 20.0, 0.0, "ha")]
    kw = dict(worlds=2, drives_per_world=3, seed=0)
    a = experiment.run(specs, **kw)
    b = experiment.run(specs, **kw)
    assert a == b                                              # same seed, same numbers
    assert a["ha"]["mean_regret_s"] < a["nearest_distance"]["mean_regret_s"]
    assert a["oracle"]["mean_regret_s"] == 0.0
