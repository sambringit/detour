"""Stage 4 charts, drawn from results/sweeps.json (4 seeds, 95% CI bands)."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from detour.stats import mean_ci

# --- design tokens (validated default palette, light mode) -------------------
SURFACE, INK, INK2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e8e7e3", "#c9c8c3"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"          # categorical slots 1-3
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # blue 100..700
SERIES = [  # (results key, label, colour)
    ("heading_aware", "Heading-aware (ours)", BLUE),
    ("nearest_distance", "Nearest by distance", ORANGE),
    ("nearest_drive_time", "Nearest by drive time", AQUA),
]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": AXIS, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})

R = json.load(open("results/sweeps.json"))
Path("figures").mkdir(exist_ok=True)


def band(ax, xs, vals, color, label, direct=True):
    m = [mean_ci(v)[0] for v in vals]
    c = [mean_ci(v)[1] for v in vals]
    ax.fill_between(xs, [a - b for a, b in zip(m, c)], [a + b for a, b in zip(m, c)],
                    color=color, alpha=0.15, linewidth=0)
    ax.plot(xs, m, color=color, lw=1.8, marker="o", ms=6, mec=SURFACE, mew=1.5, label=label)
    if direct:
        ax.annotate(label, (xs[-1], m[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=INK2)


def lines_figure(group, metric, xlabels, xlabel, titles, ylabels, fname, extra_metric=None):
    panels = [metric] + ([extra_metric] if extra_metric else [])
    fig, axes = plt.subplots(1, len(panels), figsize=(5.6 * len(panels) + 0.6, 4.1))
    axes = [axes] if len(panels) == 1 else list(axes)
    xs = list(range(len(xlabels)))
    for ax, met, title, yl in zip(axes, panels, titles, ylabels):
        for key, label, color in SERIES:
            band(ax, xs, [R[group][k][key][met] for k in R[group]], color, label)
        ax.set_xticks(xs, xlabels)
        ax.set_xlim(-0.3, len(xs) - 1 + 2.4)
        ax.set_ylim(bottom=0)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(yl)
        ax.set_title(title)
        if len(panels) == 1:
            ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2, loc="upper left")
    if len(panels) > 1:  # one shared legend below the panels, clear of the data
        h, lab = axes[0].get_legend_handles_labels()
        fig.legend(h, lab, loc="lower center", ncol=3, frameon=False, fontsize=9, labelcolor=INK2)
        fig.tight_layout(rect=[0, 0.08, 1, 1])
    else:
        fig.tight_layout()
    fig.savefig(f"figures/{fname}", dpi=160)
    plt.close(fig)


# 1) GPS noise ------------------------------------------------------------------
lines_figure(
    "noise", "mean_regret_s", ["0", "4", "8", "15", "25", "40"], "GPS position error (metres, 1 sigma)",
    ["Time lost vs the best stop", "Avoidable U-turn suggestions"],
    ["seconds lost (average)", "% of suggestions"], "fig1_noise.png", extra_metric="avoidable_uturn_pct")

# 2) POI density ----------------------------------------------------------------
lines_figure("density", "mean_regret_s", ["5", "10", "25", "50", "100"],
             "Number of stops (e.g. Starbucks) in the city",
             ["Time lost vs the best stop, by stop density"], ["seconds lost (average)"], "fig2_density.png")

# 3) U-turn penalty mismatch heatmap -----------------------------------------------
assumed, truths = [0, 10, 20, 30, 45, 60], ["10", "30", "60"]
grid = [[mean_ci(R["penalty"][t][f"ha_p{a}"]["mean_regret_s"])[0] for a in assumed] for t in truths]
base = mean_ci(R["noise"]["8"]["nearest_distance"]["mean_regret_s"])[0]
cmap = LinearSegmentedColormap.from_list("blue_seq", RAMP)
fig, ax = plt.subplots(figsize=(6.6, 3.9))
ax.grid(False)
vmax = max(max(r) for r in grid)
im = ax.imshow(grid, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
for i, row in enumerate(grid):
    for j, v in enumerate(row):
        ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=10,
                color="#ffffff" if v > 0.6 * vmax else INK)
ax.set_xticks(range(len(assumed)), [str(a) for a in assumed])
ax.set_yticks(range(len(truths)), truths)
ax.set_xlabel("U-turn penalty the scorer ASSUMES (seconds)")
ax.set_ylabel("TRUE U-turn penalty (s)")
ax.set_title(f"Time lost (s) when the assumed penalty is wrong  (nearest-by-distance: {base:.1f} s)")
for s in ax.spines.values():
    s.set_visible(False)
fig.tight_layout()
fig.savefig("figures/fig3_penalty_mismatch.png", dpi=160)
plt.close(fig)

# 4) hysteresis trade-off ----------------------------------------------------------
margins = [0, 2, 5, 10, 20, 40]
xm = [mean_ci(R["margin"]["default"][f"ha_m{m}"]["flips_per_min"]) for m in margins]
ym = [mean_ci(R["margin"]["default"][f"ha_m{m}"]["mean_regret_s"]) for m in margins]
orc = mean_ci(R["margin"]["default"]["oracle"]["flips_per_min"])[0]
fig, ax = plt.subplots(figsize=(6.6, 4.1))
ax.axvline(orc, color=INK2, lw=1, ls=(0, (4, 3)))
ax.annotate("a perfect scorer's own\nflip rate", (orc, 5.2), xytext=(6, 0), textcoords="offset points",
            fontsize=8.5, color=INK2, va="center")
ax.errorbar([a for a, _ in xm], [a for a, _ in ym], xerr=[b for _, b in xm], yerr=[b for _, b in ym],
            fmt="-", color=BLUE, lw=1.8, ecolor=BLUE, elinewidth=1, alpha=0.9, capsize=0, zorder=2)
ax.scatter([a for a, _ in xm], [a for a, _ in ym], s=60, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=3)
# margins 0, 2 and 5 s sit on top of each other (differences are inside the error bars),
# so they share one label; 10, 20 and 40 s get their own.
arrow = dict(arrowstyle="-", color=AXIS, lw=1)
ax.annotate("margin 0, 2 and 5 s:\nsame accuracy, ~same flips", (xm[1][0], ym[1][0]), xytext=(0.93, 2.3),
            textcoords="data", fontsize=8.5, color=INK2, arrowprops=arrow, va="center")
ax.annotate("margin 10 s", (xm[3][0], ym[3][0]), xytext=(-8, -16), textcoords="offset points",
            fontsize=8.5, color=INK2, ha="right")
ax.annotate("margin 20 s", (xm[4][0], ym[4][0]), xytext=(-8, 10), textcoords="offset points",
            fontsize=8.5, color=INK2, ha="right")
ax.annotate("margin 40 s", (xm[5][0], ym[5][0]), xytext=(10, 2), textcoords="offset points",
            fontsize=8.5, color=INK2)
ax.set_xlabel("suggestion changes per minute of driving (flip rate)")
ax.set_ylabel("seconds lost (average)")
ax.set_title("Hysteresis trades accuracy for fewer flips")
ax.set_ylim(bottom=0)
fig.tight_layout()
fig.savefig("figures/fig4_hysteresis.png", dpi=160)
plt.close(fig)
print("saved:", *sorted(p.name for p in Path("figures").glob("*.png")))
