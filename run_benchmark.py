"""Benchmark all scorers over many random drives in many random cities."""
import json
import random
import sys
from pathlib import Path

from detour.drive import simulate_drive
from detour.evaluate import Stats, evaluate_drive
from detour.scorers import HeadingAware, NearestByDistance, NearestByDriveTimeFree
from detour.world import GridWorld


def make_scorers():
    return [
        NearestByDistance(),
        NearestByDriveTimeFree(),
        HeadingAware(uturn_penalty=20.0, margin=0.0),   # truth is 30 s: mis-specified on purpose
        HeadingAware(uturn_penalty=20.0, margin=10.0),
    ]


def run(worlds: int = 20, drives_per_world: int = 10, pois: int = 25, seed: int = 0,
        pos_sigma: float = 8.0, head_sigma: float = 10.0):
    scorers = make_scorers()
    total = {s.name: Stats() for s in scorers}
    total["oracle"] = Stats()
    exact = n = 0
    rng = random.Random(seed)
    for w in range(worlds):
        world = GridWorld(n=30)
        world.add_pois(pois, "Starbucks", seed=seed * 1000 + w)
        for _ in range(drives_per_world):
            src = (rng.randrange(world.n), rng.randrange(world.n))
            dst = (rng.randrange(world.n), rng.randrange(world.n))
            if abs(src[0] - dst[0]) + abs(src[1] - dst[1]) < 8:
                continue  # skip trivially short drives
            ticks = simulate_drive(world, src, dst)
            stats, c = evaluate_drive(world, ticks, scorers, rng,
                                      pos_sigma=pos_sigma, head_sigma=head_sigma)
            exact, n = exact + c["single_exact"], n + c["n"]
            for name, st in stats.items():
                total[name].merge(st)
    res = {name: st.summary() for name, st in total.items()}
    res["_map_match_accuracy_pct"] = 100 * exact / n
    return res


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    res = run(seed=seed)
    print(f"{'scorer':<20}{'regret':>9}{'p90':>8}{'optimal%':>10}{'uturn%':>8}"
          f"{'avoidable%':>12}{'flips/min':>11}")
    for name, m in res.items():
        if name.startswith("_"):
            continue
        print(f"{name:<20}{m['mean_regret_s']:>8.1f}s{m['p90_regret_s']:>7.1f}s"
              f"{m['optimal_pct']:>10.1f}{m['uturn_pct']:>8.1f}"
              f"{m['avoidable_uturn_pct']:>12.1f}{m['flips_per_min']:>11.2f}")
    print(f"map-match accuracy (true street + direction): {res['_map_match_accuracy_pct']:.1f}%")
    Path("results").mkdir(exist_ok=True)
    Path("results/benchmark.json").write_text(json.dumps(res, indent=2))
    print("saved results/benchmark.json")
