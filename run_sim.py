"""Stage 1 demo: show the 'nearest stop is behind you' problem on a simulated drive."""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from detour.drive import simulate_drive
from detour.geo import angle_diff, bearing, distance
from detour.world import GridWorld


def main(seed: int = 3) -> None:
    world = GridWorld(n=30)
    world.add_pois(count=25, name="Starbucks", seed=seed)
    ticks = simulate_drive(world, src=(1, 2), dst=(27, 24))

    behind = flips = 0
    prev_id = None
    first_bad = None
    for tk in ticks:
        nearest = min(world.pois, key=lambda p: distance(tk.x, tk.y, p.x, p.y))
        rel = angle_diff(bearing(tk.x, tk.y, nearest.x, nearest.y), tk.heading)
        if rel > 90:
            behind += 1
            if first_bad is None:
                first_bad = (tk, nearest)
        if prev_id is not None and nearest.id != prev_id:
            flips += 1
        prev_id = nearest.id

    print(f"drive: {len(ticks)} ticks, {ticks[-1].t / 60:.1f} min")
    print(f"naive 'nearest by distance' pointed BEHIND the car in "
          f"{behind}/{len(ticks)} ticks ({100 * behind / len(ticks):.0f}%)")
    print(f"naive nearest changed {flips} times during the drive")

    # --- map ---
    fig, ax = plt.subplots(figsize=(7, 7))
    for k in range(world.n):
        lw = 1.4 if k % world.arterial_every == 0 else 0.4
        ax.axhline(k * world.block, color="#bbb", lw=lw, zorder=0)
        ax.axvline(k * world.block, color="#bbb", lw=lw, zorder=0)
    ax.plot([t.x for t in ticks], [t.y for t in ticks], color="#1f77b4", lw=2.5, label="drive")
    ax.scatter([p.x for p in world.pois], [p.y for p in world.pois],
               c="#2e7d32", s=40, zorder=3, label="Starbucks")
    if first_bad:
        tk, p = first_bad
        ax.scatter([tk.x], [tk.y], c="red", s=80, zorder=4, label="car (nearest is behind)")
        ax.plot([tk.x, p.x], [tk.y, p.y], "r--", lw=1.5, zorder=4)
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("Simulated drive: naive nearest-by-distance")
    fig.savefig("figures/fig0_sim_problem.png", dpi=130, bbox_inches="tight")
    print("saved figures/fig0_sim_problem.png")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
