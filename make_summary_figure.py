"""Cross-city summary chart: average seconds lost per search, three scorers, GPS 8 m / 10 deg.
Map data (c) OpenStreetMap contributors, ODbL."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from detour.stats import mean_ci

SURFACE, INK, INK2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e8e7e3", "#c9c8c3"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": AXIS, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})
SCORERS = [("nearest_distance", "Nearest by distance", ORANGE),
           ("nearest_drive_time", "Nearest by drive time", AQUA),
           ("heading_aware_tracked", "Heading-aware + track matching", BLUE)]


def load(path, cfg):
    return json.load(open(path))["results"][cfg]


PANELS = [
    ("San Francisco (real streets, older OSM snapshot)", [
        ("Starbucks\n(36)", load("results/real_sf_starbucks_p8.json", "all")),
        ("Gas stations\n(20)", load("results/real_sf_fuel_p8.json", "all")),
        ("Cafes\n(47 sampled)", load("results/real_sf_cafe_p8.json", "sparse"))]),
    ("Helsinki core (very dense, many one-ways)", [
        ("Cafes\n(80)", load("results/real_p8.json", "all")),
        ("Cafes\n(20 sampled)", load("results/real_p8.json", "sparse"))]),
]
fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.3), gridspec_kw={"width_ratios": [3, 2.3]})
w = 0.26
for ax, (title, groups) in zip(axes, PANELS):
    for gi, (gname, res) in enumerate(groups):
        for si, (key, label, color) in enumerate(SCORERS):
            m, c = mean_ci(res[key]["mean_regret_s"])
            x = gi + (si - 1) * (w + 0.02)
            ax.bar(x, m, w, color=color, edgecolor=SURFACE, linewidth=2, label=label, zorder=3)
            ax.annotate(f"{m:.1f}", (x, m), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5, color=INK2)
    ax.set_xticks(range(len(groups)), [g for g, _ in groups])
    ax.set_xlim(-0.6, len(groups) - 0.4)
    ax.set_ylabel("seconds lost vs the best stop (average)")
    ax.set_title(title)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.08)
h, lab = axes[0].get_legend_handles_labels()
fig.legend(h[:3], lab[:3], loc="lower center", ncol=3, frameon=False, fontsize=9, labelcolor=INK2)
fig.tight_layout(rect=[0, 0.07, 1, 1])
fig.savefig("figures/fig7_cities.png", dpi=160)
print("saved figures/fig7_cities.png")
