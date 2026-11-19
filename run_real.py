"""Stage 5: the same benchmark on a REAL road network (OpenStreetMap) with real POIs.

    python3 run_real.py                                   # bundled Helsinki sample + its real cafes
    python3 run_real.py --osm data/atlanta.osm.gz --tag amenity=fuel --name "Gas station"

Map data (c) OpenStreetMap contributors, ODbL."""
import argparse
import json
from pathlib import Path

from detour import experiment
from detour.osm import load_osm
from detour.stats import mean_ci

SPECS = [("dist",), ("free",), ("ha", 20.0, 0.0, "heading_aware"),
         ("ha", 20.0, 0.0, "heading_aware_tracked", True)]
METRICS = [("mean_regret_s", "time lost (s)"), ("optimal_pct", "best stop %"),
           ("avoidable_uturn_pct", "avoidable U-turn %"), ("flips_per_min", "flips/min")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", default="data/helsinki/Helsinki.osm.bz2")
    ap.add_argument("--tag", default="amenity=cafe", help="key=value of the POI nodes to use")
    ap.add_argument("--name", default="Cafe")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--drives", type=int, default=40, help="drives per seed")
    ap.add_argument("--pos-sigma", type=float, default=8.0, help="GPS position noise, meters")
    ap.add_argument("--head-sigma", type=float, default=10.0, help="GPS heading noise, degrees")
    ap.add_argument("--min-dist", type=float, default=500.0, help="min straight-line trip length, m")
    ap.add_argument("--configs", default="all,sparse", help="all = every POI, sparse = 1/4 of them")
    ap.add_argument("--out", default="results/real.json")
    a = ap.parse_args()

    key, _, val = a.tag.partition("=")
    net, n_poi = load_osm(a.osm, poi_tag=(key, val or None), poi_name=a.name)
    base = list(net.pois)
    n_edges = sum(len(v) for v in net.out.values())
    one_way = sum(1 for u in net.out for v in net.out[u] if not net.has_edge(v, u))
    print(f"network: {len(net.pos)} nodes, {n_edges} directed edges ({one_way} one-way), "
          f"{sum(net.uturn_ok.values())} intersections/dead-ends, {n_poi} real '{a.name}' POIs")
    if n_poi < 8:
        raise SystemExit("too few real POIs in this extract; choose another --tag or area")

    results = {}
    wanted = a.configs.split(",")
    for label, subset in [("all", None), ("sparse", max(5, n_poi // 4))]:
        if label not in wanted:
            continue
        per_seed = [experiment.run_real(net, base, SPECS, seed=s, drives=a.drives, poi_subset=subset, min_dist=a.min_dist,
                            pos_sigma=a.pos_sigma, head_sigma=a.head_sigma)
                    for s in range(a.seeds)]
        agg = {}
        for name in per_seed[0]:
            if name.startswith("_"):
                agg[name] = [r[name] for r in per_seed]
            else:
                agg[name] = {m: [r[name][m] for r in per_seed] for m, _ in METRICS}
        results[label] = agg
        k = len(base) if subset is None else subset
        print(f"\n--- {k} POIs ({label}), {a.seeds} seeds x {a.drives} drives ---")
        print(f"{'scorer':<20}" + "".join(f"{d:>22}" for _, d in METRICS))
        for name in ["nearest_distance", "nearest_drive_time", "heading_aware",
                     "heading_aware_tracked", "oracle"]:
            cells = []
            for m, _ in METRICS:
                mu, ci = mean_ci(agg[name][m])
                cells.append(f"{mu:>14.1f} ±{ci:<5.1f}")
            print(f"{name:<20}" + "".join(cells))
        mm = {k: mean_ci(agg[k])[0] for k in agg if k.startswith("_")}
        print(f"map-match exact/near: single-fix {mm['_map_match_accuracy_pct']:.0f}%/"
              f"{mm['_single_near_pct']:.0f}%, track-aware {mm['_track_exact_pct']:.0f}%/{mm['_track_near_pct']:.0f}%")

    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"source": a.osm, "pos_sigma": a.pos_sigma, "head_sigma": a.head_sigma, "pois": n_poi, "nodes": len(net.pos), "edges": n_edges,
         "one_way_edges": one_way, "results": results}, indent=1))
    print("\nsaved", a.out)


if __name__ == "__main__":
    main()
