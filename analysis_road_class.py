"""Where does heading matter? Split the benchmark by the kind of road the car is on.

    python3 analysis_road_class.py --osm data/san_francisco/sfsubset.osm --tag "name=~Starbucks"

fast = the car is on a road with speed >= 60 km/h (motorway/trunk/primary/secondary);
slow = everything else. Same simulation, noise and scorers as run_real.py."""
import argparse
import random
from collections import defaultdict

from detour.drive import simulate_drive
from detour.evaluate import Stats
from detour.experiment import build_scorers
from detour.obs import observe
from detour.osm import load_osm
from detour.stats import mean_ci
from detour.truth import eta, ground_truth

SPECS = [("dist",), ("free",), ("ha", 20.0, 0.0, "heading_aware_tracked", True)]
FAST_MS = 60 / 3.6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--name", default="POI")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--drives", type=int, default=30)
    ap.add_argument("--min-dist", type=float, default=1500.0)
    a = ap.parse_args()
    key, _, val = a.tag.partition("=")
    net, k = load_osm(a.osm, poi_tag=(key, val or None), poi_name=a.name)
    nodes = sorted(net.pos)
    per_seed = []  # one {(class, scorer): Stats} per seed
    for seed in range(a.seeds):
        rng = random.Random(seed)
        scorers = build_scorers(SPECS)
        stats = defaultdict(Stats)
        share = defaultdict(int)
        done = 0
        while done < a.drives:
            s, d = rng.choice(nodes), rng.choice(nodes)
            (sx, sy), (dx, dy) = net.xy(s), net.xy(d)
            if ((sx - dx) ** 2 + (sy - dy) ** 2) ** 0.5 < a.min_dist:
                continue
            ticks = simulate_drive(net, s, d)
            if len(ticks) < 20:
                continue
            for sc in scorers:
                sc.reset() if hasattr(sc, "reset") else None
            for tk in ticks[::3]:
                ob = observe(tk, rng)
                _, best, _ = ground_truth(net, tk)
                cls = "fast" if tk.speed >= FAST_MS else "slow"
                share[cls] += 1
                for sc in scorers:
                    e, ut = eta(net, tk, sc.pick(net, ob))
                    st = stats[(cls, sc.name)]
                    st.ticks += 1
                    st.regret_sum += e - best
                    st.optimal += (e - best) < 1e-6
                    st.uturn += ut
            done += 1
        per_seed.append((stats, share))
    tot = {c: sum(s[1][c] for s in per_seed) for c in ("fast", "slow")}
    print(f"{k} '{a.name}' POIs; share of driving time on fast roads: "
          f"{100 * tot['fast'] / (tot['fast'] + tot['slow']):.0f}%")
    print(f"{'road':<6}{'scorer':<24}{'time lost (s)':>16}{'best stop %':>14}")
    for cls in ("fast", "slow"):
        for sc in scorers:
            reg = [s[0][(cls, sc.name)].regret_sum / max(s[0][(cls, sc.name)].ticks, 1) for s in per_seed]
            opt = [100 * s[0][(cls, sc.name)].optimal / max(s[0][(cls, sc.name)].ticks, 1) for s in per_seed]
            (m, c), (o, _) = mean_ci(reg), mean_ci(opt)
            print(f"{cls:<6}{sc.name:<24}{m:>10.1f} ±{c:<4.1f}{o:>14.1f}")


if __name__ == "__main__":
    main()
