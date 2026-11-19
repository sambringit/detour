"""Stage 5 charts from the real-road runs (results/real_p*.json) + an example map.
Map data (c) OpenStreetMap contributors, ODbL."""
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from detour.drive import simulate_drive
from detour.evaluate import UTURN_PENALTY
from detour.obs import observe
from detour.osm import load_osm
from detour.scorers import HeadingAware, NearestByDistance
from detour.stats import mean_ci
from detour.truth import eta, ground_truth
from detour.world import POI

SURFACE, INK, INK2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e8e7e3", "#c9c8c3"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": AXIS, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})
Path("figures").mkdir(exist_ok=True)

# ---- figure 5: time lost vs GPS noise on real roads -----------------------------------
SERIES = [  # key, label, colour, linestyle, hollow marker?
    ("heading_aware_tracked", "Heading-aware + track matching", BLUE, "-", False),
    ("heading_aware", "Heading-aware, single-fix matching", BLUE, (0, (4, 2)), True),
    ("nearest_distance", "Nearest by distance", ORANGE, "-", False),
    ("nearest_drive_time", "Nearest by drive time", AQUA, "-", False),
]
levels = [("3", "3 m"), ("8", "8 m"), ("15", "15 m")]
runs = {k: json.load(open(f"results/real_p{k}.json")) for k, _ in levels}
fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.2))
for ax, (cfg, title) in zip(axes, [("all", "Dense: all 80 real cafes"), ("sparse", "Sparse: 20 cafes (like gas stations)")]):
    xs = range(len(levels))
    for key, label, color, ls, hollow in SERIES:
        stats = [mean_ci(runs[k]["results"][cfg][key]["mean_regret_s"]) for k, _ in levels]
        m, c = [s[0] for s in stats], [s[1] for s in stats]
        ax.fill_between(xs, [a - b for a, b in zip(m, c)], [a + b for a, b in zip(m, c)],
                        color=color, alpha=0.12, linewidth=0)
        ax.plot(xs, m, color=color, ls=ls, lw=1.8, marker="o", ms=6, mec=color if hollow else SURFACE,
                mfc=SURFACE if hollow else color, mew=1.5, label=label)
    ax.set_xticks(list(xs), [l for _, l in levels])
    ax.set_xlim(-0.25, 2.25)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("GPS position error (1 sigma)")
    ax.set_ylabel("seconds lost vs the best stop (average)")
    ax.set_title(title)
h, lab = axes[0].get_legend_handles_labels()
fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, fontsize=8.5, labelcolor=INK2)
fig.tight_layout(rect=[0, 0.08, 1, 1])
fig.savefig("figures/fig5_real_roads.png", dpi=160)
plt.close(fig)

# ---- figure 6: one real moment, Helsinki ------------------------------------------------
net, _ = load_osm("data/helsinki/Helsinki.osm.bz2", poi_tag=("amenity", "cafe"), poi_name="Cafe")
base = list(net.pois)
naive, ours = NearestByDistance(), HeadingAware(20.0, 0.0, "ours", tracked=True)
found = None
nodes = sorted(net.pos)
for seed in range(40):
    rng = random.Random(seed)
    net.pois = [POI(i, p.name, p.node, p.x, p.y) for i, p in enumerate(rng.sample(base, 20))]
    src, dst = rng.choice(nodes), rng.choice(nodes)
    ticks = simulate_drive(net, src, dst)
    if len(ticks) < 60:
        continue
    ours.reset()
    for tk in ticks[::3]:
        ob = observe(tk, rng)
        a, b = naive.pick(net, ob), ours.pick(net, ob)
        ea, ua = eta(net, tk, a)
        eb, ub = eta(net, tk, b)
        best = ground_truth(net, tk)[1]
        if tk.t > 15 and ea - best > 70 and eb - best < 1 and (found is None or ea - eb > found[0]):
            found = (ea - eb, seed, ticks, tk, a, b, ea, eb, ua)
    if found and found[0] > 90:
        break
gap, seed, ticks, tk, a, b, ea, eb, ua = found
net.pois = [POI(i, p.name, p.node, p.x, p.y) for i, p in enumerate(random.Random(seed).sample(base, 20))]

fig, ax = plt.subplots(figsize=(6.4, 7.6))
ax.grid(False)
for u, nbrs in net.out.items():
    for v in nbrs:
        if u < v or not net.has_edge(v, u):
            (x1, y1), (x2, y2) = net.xy(u), net.xy(v)
            ax.plot([x1, x2], [y1, y2], color=AXIS, lw=0.9, zorder=1, solid_capstyle="round")
ax.plot([t.x for t in ticks], [t.y for t in ticks], color=BLUE, lw=2.2, alpha=0.35, zorder=2)
ax.scatter([p.x for p in net.pois], [p.y for p in net.pois], s=28, color=INK2, zorder=3)
for pick, color, mk, lab in [(a, ORANGE, "s", f"nearest by distance: {ea:.0f} s away"),
                             (b, BLUE, "*", f"heading-aware: {eb:.0f} s away")]:
    ax.plot([tk.x, pick.x], [tk.y, pick.y], color=color, lw=1.4, ls=(0, (4, 3)), zorder=4)
    ax.scatter([pick.x], [pick.y], s=130 if mk == "*" else 70, marker=mk, color=color,
               edgecolor=SURFACE, linewidth=1.2, zorder=5, label=lab)
ax.scatter([tk.x], [tk.y], s=110, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=6, label="car (blue line = its route)")
import math
ax.annotate("", xy=(tk.x + 55 * math.sin(math.radians(tk.heading)), tk.y + 55 * math.cos(math.radians(tk.heading))),
            xytext=(tk.x, tk.y), arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2), zorder=7)
ax.set_aspect("equal")
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_visible(False)
ax.legend(loc="lower left", frameon=False, fontsize=8.5, labelcolor=INK2)
ax.set_title("Real streets (Helsinki): the closest cafe is a long way round")
fig.tight_layout()
fig.savefig("figures/fig6_helsinki_example.png", dpi=160)
print(f"example: gap {gap:.0f} s, naive needs U-turn: {ua}")
