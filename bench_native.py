"""Time the optional C++ cost_to_go against the pure-Python one.

    python3 bench_native.py                 # full run (a few minutes)
    python3 bench_native.py --quick         # smoke run, rough numbers only
    python3 bench_native.py --out results/bench_native.json

Needs the extension built and numpy:  pip install -e ".[native]"

What is timed (all with time.perf_counter, garbage collection paused during each timing,
repetitions interleaved and the order rotated so drift or warm-up cannot favour one side):

 1. cost_to_go on one network, uncached, a fixed set of targets, penalty 20 s:
      python      RoadNetwork._cost_to_go_python        (the reference implementation)
      cpp_arrays  the C++ search alone, results left as numpy arrays
      cpp_dict    C++ search + conversion to {(u, v): (seconds, flag)}  <- what
                  RoadNetwork.cost_to_go returns, so this is the fair like-for-like number
    plus the one-time cost of building the native snapshot (NativeGraph).
 2. A full evaluation (map matching, scoring, ground truth, statistics) with the native path
    on and off, on GridWorld (experiment.run) and on a real extract (experiment.run_real).
    Caches and the native snapshot start cold in every repetition. Only cost_to_go is
    accelerated; the rest of the evaluation is unchanged Python, so the speedup is smaller.

Every repetition also checks that both paths return identical results. Only measured numbers
are reported. Timings depend on the machine; the JSON records which one this was.
"""
from __future__ import annotations

import argparse
import cProfile
import gc
import json
import os
import platform
import pstats
import random
import statistics
import sys
import time
from pathlib import Path

from detour import experiment, native
from detour.osm import load_osm
from detour.world import GridWorld

PENALTY = 20.0
GRID_SPECS = [("dist",), ("free",), ("ha", 20.0, 0.0, "heading_aware"),
              ("ha", 20.0, 10.0, "heading_aware_hys")]          # the four scorers of run_benchmark.py
REAL_SPECS = GRID_SPECS + [("ha", 20.0, 0.0, "heading_aware_tracked", True)]  # as in run_real.py
EXTRACTS = {"helsinki": "data/helsinki/Helsinki.osm.bz2", "san_francisco": "data/san_francisco/sfsubset.osm.bz2"}


def timed(fn):
    gc.collect()
    gc.disable()
    try:
        t0 = time.perf_counter()
        out = fn()
        return time.perf_counter() - t0, out
    finally:
        gc.enable()


def summarize(xs):
    return {"median": statistics.median(xs), "min": min(xs), "max": max(xs), "n": len(xs), "raw": xs}


def machine() -> dict:
    cpu = platform.processor() or ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    if sys.platform == "darwin":
        import subprocess
        try:
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                 text=True, check=True).stdout.strip() or cpu
        except Exception:
            pass
    return {"platform": platform.platform(), "python": platform.python_version(), "cpu": cpu,
            "cpu_count": os.cpu_count(), "numpy": native.np.__version__ if native.np else None}


# --- 1. cost_to_go micro-benchmark ------------------------------------------------------
def bench_ctg(label, net, n_targets, reps, seed=0):
    nodes = sorted(net.pos, key=repr)
    targets = random.Random(seed).sample(nodes, min(n_targets, len(nodes)))
    ng = native.NativeGraph(net, cache=False)
    variants = {
        "python": lambda: [net._cost_to_go_python(t, PENALTY) for t in targets],
        "cpp_arrays": lambda: [ng.cost_to_go_arrays(t, PENALTY) for t in targets],
        "cpp_dict": lambda: [ng.cost_to_go(t, PENALTY) for t in targets],
    }
    # parity on exactly these targets, outside the timings
    for t in targets:
        assert net._cost_to_go_python(t, PENALTY) == ng.cost_to_go(t, PENALTY), f"parity failed {label} {t!r}"
    for fn in variants.values():  # warm-up
        fn()
    times = {k: [] for k in variants}
    names = list(variants)
    for r in range(reps):
        for k in names[r % 3:] + names[:r % 3]:  # rotate the order each repetition
            dt, _ = timed(variants[k])
            times[k].append(dt / len(targets) * 1000.0)  # ms per call
    build = [timed(lambda: native.NativeGraph(net, cache=False))[0] * 1000.0 for _ in range(reps)]
    states = sum(len(v) for v in net.out.values())
    res = {"label": label, "nodes": len(net.pos), "directed_edges": states, "targets": len(targets),
           "penalty": PENALTY, "ms_per_call": {k: summarize(v) for k, v in times.items()},
           "snapshot_build_ms": summarize(build)}
    py = res["ms_per_call"]["python"]["median"]
    res["speedup_vs_python"] = {k: py / res["ms_per_call"][k]["median"] for k in ("cpp_arrays", "cpp_dict")}
    return res


# --- 2. full evaluation ----------------------------------------------------------------------
def set_native(on: bool) -> None:
    os.environ["DETOUR_NATIVE"] = "1" if on else "0"


def bench_eval(label, make_run, reps):
    """make_run() -> callable executing one cold evaluation and returning its metrics dict."""
    modes = {"python": False, "cpp": True}
    times = {m: [] for m in modes}
    results = {}
    for r in range(reps + 1):  # repetition 0 is an untimed warm-up of imports/bytecode
        order = list(modes) if r % 2 == 0 else list(modes)[::-1]
        for m in order:
            set_native(modes[m])
            run = make_run()
            dt, res = timed(run)
            if r > 0:
                times[m].append(dt)
            results.setdefault(r, {})[m] = res
        assert results[r]["python"] == results[r]["cpp"], f"{label}: results differ between paths (rep {r})"
    set_native(True)
    out = {"label": label, "seconds": {m: summarize(v) for m, v in times.items()},
           "identical_results_every_rep": True}
    out["speedup"] = out["seconds"]["python"]["median"] / out["seconds"]["cpp"]["median"]
    return out


def ctg_wall_share(make_run, on: bool, reps: int = 3):
    """Wall-clock share of one evaluation spent inside cost_to_go (and, in native mode, the
    snapshot build). Only those calls are timed, so the share is not distorted by a profiler."""
    from detour.world import RoadNetwork

    set_native(on)
    shares, totals, calls = [], [], []
    for _ in range(reps):
        acc = {"t": 0.0, "n": 0}

        def wrap(f, acc=acc):
            def g(*a, **k):
                t0 = time.perf_counter()
                try:
                    return f(*a, **k)
                finally:
                    acc["t"] += time.perf_counter() - t0
                    acc["n"] += 1
            return g

        saved = (RoadNetwork._cost_to_go_python, native.NativeGraph.cost_to_go, native.NativeGraph.__init__)
        RoadNetwork._cost_to_go_python = wrap(saved[0])
        native.NativeGraph.cost_to_go = wrap(saved[1])
        native.NativeGraph.__init__ = wrap(saved[2])
        try:
            run = make_run()
            dt, _ = timed(run)
        finally:
            RoadNetwork._cost_to_go_python, native.NativeGraph.cost_to_go, native.NativeGraph.__init__ = saved
        shares.append(acc["t"] / dt)
        totals.append(dt)
        calls.append(acc["n"])
    set_native(True)
    return {"share_median": statistics.median(shares), "shares": shares, "total_s_median": statistics.median(totals),
            "timed_calls": calls[0]}


def top_functions(make_run, on: bool, k: int = 6):
    """Biggest self-time functions (cProfile; only the ORDER is meaningful, not the percentages)."""
    set_native(on)
    run = make_run()
    pr = cProfile.Profile()
    pr.enable()
    run()
    pr.disable()
    st = pstats.Stats(pr)
    rows = sorted(st.stats.items(), key=lambda kv: kv[1][2], reverse=True)[:k]
    set_native(True)
    return [f"{Path(fn).name}:{name}" for (fn, _, name), _ in rows]


SECTIONS = ("micro", "grid", "real", "profile")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=SECTIONS, default=list(SECTIONS),
                    help="run just these sections; results are merged into --out if it exists")
    ap.add_argument("--reps", type=int, default=9, help="repetitions for the cost_to_go timings")
    ap.add_argument("--eval-reps", type=int, default=5, help="repetitions for the full evaluations")
    ap.add_argument("--quick", action="store_true", help="tiny settings for a smoke run")
    ap.add_argument("--no-sf", action="store_true", help="skip the San Francisco extract")
    ap.add_argument("--grid-worlds", type=int, default=20)
    ap.add_argument("--grid-drives", type=int, default=10)
    ap.add_argument("--real-drives", type=int, default=40)
    ap.add_argument("--out", default="results/bench_native.json")
    a = ap.parse_args()
    if not native.available:
        raise SystemExit("C++ extension not available: build it with  pip install -e '.[native]'")
    if a.quick:
        a.reps, a.eval_reps, a.grid_worlds, a.grid_drives, a.real_drives = 3, 2, 2, 4, 6

    out_path = Path(a.out)
    report = json.loads(out_path.read_text()) if out_path.exists() else {}
    report.update({"machine": machine(), "cost_to_go": report.get("cost_to_go", []),
                   "evaluation": report.get("evaluation", {})})
    report.setdefault("settings", {}).update({k: v for k, v in vars(a).items() if k != "only"})
    print("machine:", report["machine"])
    root = Path(__file__).resolve().parent

    def save():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=1))

    def load(name):
        net, _ = load_osm(str(root / EXTRACTS[name]), poi_tag=("amenity", "cafe"), poi_name="Cafe")
        return net

    if "micro" in a.only:
        nets = {"GridWorld(30)": GridWorld(n=30), "helsinki": load("helsinki")}
        if not a.no_sf:
            nets["san_francisco"] = load("san_francisco")
        print("\n== cost_to_go, ms per call (median of %d reps; uncached, penalty %.0f s) ==" % (a.reps, PENALTY))
        print(f"{'network':<16}{'edges':>8}{'python':>10}{'cpp_arrays':>12}{'cpp_dict':>10}{'x arrays':>10}{'x dict':>8}{'snapshot':>10}")
        report["cost_to_go"] = []
        for label, net in nets.items():
            r = bench_ctg(label, net, 15 if label == "san_francisco" else 40, a.reps)
            report["cost_to_go"].append(r)
            m = r["ms_per_call"]
            print(f"{label:<16}{r['directed_edges']:>8}{m['python']['median']:>10.3f}{m['cpp_arrays']['median']:>12.3f}"
                  f"{m['cpp_dict']['median']:>10.3f}{r['speedup_vs_python']['cpp_arrays']:>9.1f}x"
                  f"{r['speedup_vs_python']['cpp_dict']:>7.1f}x{r['snapshot_build_ms']['median']:>8.2f}ms")
        save()

    makers = {}

    def make_grid():
        return lambda: experiment.run(GRID_SPECS, seed=0, worlds=a.grid_worlds,
                                      drives_per_world=a.grid_drives, pois=25)

    makers["grid"] = ("GridWorld(30) experiment.run", make_grid)
    if "real" in a.only or "profile" in a.only:
        net = load("helsinki")
        base = list(net.pois)

        def make_helsinki():
            net.clear_caches()
            net._native = None  # cold snapshot too: building it is part of the cost
            return lambda: experiment.run_real(net, base, REAL_SPECS, seed=0, drives=a.real_drives)
        makers["real"] = ("Helsinki experiment.run_real", make_helsinki)

    for key in ("grid", "real"):
        if key in a.only:
            label, make_run = makers[key]
            print("\n== full evaluation, seconds (median of %d reps, cold caches, identical results checked) ==" % a.eval_reps)
            print(f"{'evaluation':<32}{'python':>10}{'cpp':>10}{'speedup':>9}")
            r = bench_eval(label, make_run, a.eval_reps)
            report["evaluation"][key] = {**report["evaluation"].get(key, {}), **r}
            s = r["seconds"]
            print(f"{label:<32}{s['python']['median']:>10.2f}{s['cpp']['median']:>10.2f}{r['speedup']:>8.2f}x")
            save()

    if "profile" in a.only:
        print("\n== share of wall-clock time inside cost_to_go (median of 3 runs; native mode includes snapshot build) ==")
        for key, (label, make_run) in makers.items():
            wp, wc = ctg_wall_share(make_run, False), ctg_wall_share(make_run, True)
            top = top_functions(make_run, True)
            report["evaluation"].setdefault(key, {"label": label}).update(
                {"ctg_share_python_mode": wp, "ctg_share_cpp_mode": wc, "top_self_time_cpp_mode": top})
            print(f"{label:<32} python mode {100 * wp['share_median']:.0f}% of {wp['total_s_median']:.2f}s | "
                  f"cpp mode {100 * wc['share_median']:.0f}% of {wc['total_s_median']:.2f}s")
            print("   remaining self-time leaders (cpp mode):", ", ".join(top))
        save()
    print("\nsaved", a.out)


if __name__ == "__main__":
    main()
