"""One reproducible experiment: many random cities x many random drives -> metrics."""
from __future__ import annotations

import random
from collections import Counter

from .drive import simulate_drive
from .evaluate import Stats, evaluate_drive
from .scorers import HeadingAware, NearestByDistance, NearestByDriveTimeFree
from .world import GridWorld


def _match_pcts(mc) -> dict:
    n = mc["n"]
    return {"_map_match_accuracy_pct": 100 * mc["single_exact"] / n,
            "_single_near_pct": 100 * mc["single_near"] / n,
            "_track_exact_pct": 100 * mc["track_exact"] / n,
            "_track_near_pct": 100 * mc["track_near"] / n}


def build_scorers(specs):
    """specs: ("dist",) | ("free",) | ("ha", uturn_penalty, margin, name[, tracked])"""
    out = []
    for s in specs:
        if s[0] == "dist":
            out.append(NearestByDistance())
        elif s[0] == "free":
            out.append(NearestByDriveTimeFree())
        elif s[0] == "ha":
            out.append(HeadingAware(uturn_penalty=s[1], margin=s[2], name=s[3],
                                    tracked=len(s) > 4 and bool(s[4])))
        else:
            raise ValueError(s)
    return out


def run_real(net, base_pois, specs, seed=0, drives=60, poi_subset=None, min_dist=500.0,
             pos_sigma=8.0, head_sigma=10.0, truth_penalty=30.0):
    """Same grading as run(), but on a REAL road network (from detour.osm) with real POIs.
    Drives are simulated between random nodes; poi_subset=k samples k of the real POIs
    per seed (to mimic a sparser category such as gas stations)."""
    from math import hypot

    from .world import POI

    rng = random.Random(seed)
    chosen = base_pois if poi_subset is None else rng.sample(base_pois, poi_subset)
    if poi_subset is not None:
        net.clear_caches()  # different POIs every seed: don't let cached routes pile up
    net.pois = [POI(i, p.name, p.node, p.x, p.y) for i, p in enumerate(chosen)]
    scorers = build_scorers(specs)
    total = {s.name: Stats() for s in scorers}
    total["oracle"] = Stats()
    mc = Counter()
    done = 0
    nodes = sorted(net.pos)
    while done < drives:
        src, dst = rng.choice(nodes), rng.choice(nodes)
        (sx, sy), (dx, dy) = net.xy(src), net.xy(dst)
        if hypot(sx - dx, sy - dy) < min_dist:
            continue
        ticks = simulate_drive(net, src, dst)
        if len(ticks) < 20:
            continue
        stats, c = evaluate_drive(net, ticks, scorers, rng, pos_sigma=pos_sigma,
                                  head_sigma=head_sigma, truth_penalty=truth_penalty)
        mc.update(c)
        done += 1
        for name, st in stats.items():
            total[name].merge(st)
    res = {name: st.summary() for name, st in total.items()}
    res.update(_match_pcts(mc))
    return res


def run(specs, seed=0, worlds=8, drives_per_world=8, pois=25, n=30,
        pos_sigma=8.0, head_sigma=10.0, truth_penalty=30.0):
    scorers = build_scorers(specs)
    total = {s.name: Stats() for s in scorers}
    total["oracle"] = Stats()
    mc = Counter()
    rng = random.Random(seed)
    for w in range(worlds):
        world = GridWorld(n=n)
        world.add_pois(pois, "Starbucks", seed=seed * 1000 + w)
        for _ in range(drives_per_world):
            src = (rng.randrange(n), rng.randrange(n))
            dst = (rng.randrange(n), rng.randrange(n))
            if abs(src[0] - dst[0]) + abs(src[1] - dst[1]) < 8:
                continue
            ticks = simulate_drive(world, src, dst)
            stats, c = evaluate_drive(world, ticks, scorers, rng, pos_sigma=pos_sigma,
                                      head_sigma=head_sigma, truth_penalty=truth_penalty)
            mc.update(c)
            for name, st in stats.items():
                total[name].merge(st)
    res = {name: st.summary() for name, st in total.items()}
    res.update(_match_pcts(mc))
    return res
