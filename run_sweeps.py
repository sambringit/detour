"""Stage 4: sensitivity sweeps. Writes results/sweeps.json (per-seed values for CIs).

    python3 run_sweeps.py            # full run
    python3 run_sweeps.py --quick    # tiny smoke run
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from detour import experiment

BASE = [("dist",), ("free",), ("ha", 20.0, 0.0, "heading_aware")]


def jobs(seeds, worlds, drives):
    common = dict(worlds=worlds, drives_per_world=drives)
    out = []
    for s in seeds:
        # 1) GPS noise: (position sigma m, heading sigma deg)
        for ps, hs in [(0, 0), (4, 5), (8, 10), (15, 20), (25, 30), (40, 45)]:
            out.append(("noise", str(ps), dict(specs=BASE, seed=s, pos_sigma=ps, head_sigma=hs, **common)))
        # 2) POI density: how many Starbucks in the 6 km x 6 km city
        for p in [5, 10, 25, 50, 100]:
            out.append(("density", str(p), dict(specs=BASE, seed=s, pois=p, **common)))
        # 3) U-turn penalty mismatch: scorer assumes X, the truth is Y
        assumed = [0, 10, 20, 30, 45, 60]
        specs = [("ha", float(a), 0.0, f"ha_p{a}") for a in assumed]
        for truth in [10, 30, 60]:
            out.append(("penalty", str(truth), dict(specs=specs, seed=s, truth_penalty=float(truth), **common)))
        # 4) hysteresis margin (seconds a rival must be faster before we switch)
        margins = [0, 2, 5, 10, 20, 40]
        specs = [("ha", 20.0, float(m), f"ha_m{m}") for m in margins]
        out.append(("margin", "default", dict(specs=specs, seed=s, **common)))
    return out


def one(job):
    group, key, cfg = job
    return group, key, cfg["seed"], experiment.run(**cfg)


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    seeds = [0] if quick else [0, 1, 2, 3]
    worlds, drives = (2, 3) if quick else (6, 6)
    todo = jobs(seeds, worlds, drives)
    results: dict = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(one, j) for j in todo]
        for i, f in enumerate(as_completed(futs), 1):
            group, key, seed, res = f.result()
            g = results.setdefault(group, {}).setdefault(key, {})
            for name, m in res.items():
                if name.startswith("_"):
                    g.setdefault(name, []).append(m)
                else:
                    for metric, v in m.items():
                        g.setdefault(name, {}).setdefault(metric, []).append(v)
            print(f"[{i}/{len(todo)}] {group}={key} seed={seed}  ({time.time() - t0:.0f}s)", flush=True)
    Path("results").mkdir(exist_ok=True)
    out = "results/sweeps_quick.json" if quick else "results/sweeps.json"
    Path(out).write_text(json.dumps(results, indent=1))
    print("saved", out, f"in {time.time() - t0:.0f}s")
