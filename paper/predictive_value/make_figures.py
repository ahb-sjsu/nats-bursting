"""Generate the three paper figures from theory + battery artifacts.
Run from paper/predictive_value/ (needs battery_v4/v5/v5b/v5c JSONs here).
Gotcha: matplotlib mathtext needs \\frac{1}{2} (no \\frac12, no \\tfrac).
"""
import json

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams.update({"font.size": 8.5, "axes.labelsize": 8.5,
                     "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
                     "legend.fontsize": 7.2, "figure.dpi": 200})
BLUE, ORANGE, TEAL, GREY, RED = "#3d6fb4", "#d97e3d", "#3f9d83", "#8a8f98", "#c65a5a"

# ---- Fig 1: trichotomy + sign branches (exact curves) ----
fig, ax = plt.subplots(figsize=(3.6, 2.6))
pi, ps, ds = 0.35, 0.45, 2.0
ap, am = (ps - pi) * pi, (ps - pi) * (1 - pi)
Cmin, Cmax = -pi**2, pi * (1 - pi)
C = np.linspace(Cmin, Cmax, 400)
hinge = np.where(C >= 0, ds * np.maximum(C - ap, 0), ds * np.maximum(-C - am, 0))
ax.plot(C, hinge, color=BLUE, lw=2, label=r"polyhedral, $\pi{=}.35$, $p^*{=}.45$")
ax.plot(C, 2 * np.abs(C), color=GREY, lw=1.6, ls="--",
        label=r"symmetric ($\pi{=}p^*{=}\frac{1}{2}$): threshold-free")
ax.plot(C, C**2 / (pi * (1 - pi)), color=TEAL, lw=1.8, ls="-.",
        label="squared error: quadratic")
ax.axvspan(-am, ap, color=BLUE, alpha=0.08)
ax.annotate("dead zone", xy=((ap - am) / 2, 0.012), ha="center", fontsize=7, color=BLUE)
ax.axvline(0, color="0.85", lw=0.6)
ax.set_xlabel(r"lag covariance $C(D)$")
ax.set_ylabel(r"value of the delayed sample $\Delta$")
ax.set_xlim(Cmin, 0.19)
ax.set_ylim(-0.005, 0.31)
ax.legend(loc="upper left", framealpha=0.9)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("fig_trichotomy.pdf")

# ---- Fig 2: tightness vs the SYMMETRIC law |r|/2 ----
# (the ratio to V1 lifts off at small r for mildly imbalanced series ---
#  that is the hinge threshold of Fig 1, deliberately kept out of this panel)
fig, ax = plt.subplots(figsize=(3.6, 2.6))
r = np.linspace(1e-4, 0.995, 400)
I = 0.5 * ((1 + r) * np.log(1 + r) + (1 - r) * np.log(1 - r))
ax.plot(r, np.sqrt(2 * I) / r, color=BLUE, lw=2,
        label=r"exact ratio $\sqrt{I(r)/2}\,/\,(|r|/2)$")
ax.plot(r, 1 + r**2 / 12, color=GREY, lw=1.2, ls="--",
        label=r"$1+r^2/12$ (leading correction)")
d4 = json.load(open("battery_v4.json"))
markers = {"Two-state Markov": "o", "i.i.d. null": "s", "LOCATA azimuth": "^",
           "Sperm-whale codas": "D", "GOES protons": "v"}
for dom in d4["domains"]:
    if abs(dom["pi"] - 0.5) > 0.035 or dom["title"] not in markers:
        continue
    rr = np.abs(np.array(dom["r"]))
    I1 = np.array(dom["I_nats"])
    m = rr > 0.05
    if m.sum() < 2:
        continue
    ax.scatter(rr[m], np.sqrt(np.maximum(I1[m], 0) / 2) / (rr[m] / 2), s=11,
               alpha=0.6, marker=markers[dom["title"]], label=dom["title"])
ax.set_xlabel(r"$|r(D)|$")
ax.set_ylabel(r"envelope / symmetric law $\frac{1}{2}|r|$")
ax.set_xlim(0, 1.0)
ax.set_ylim(0.985, 1.20)
ax.legend(loc="upper left", framealpha=0.9)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("fig_tightness.pdf")

# ---- Fig 3: battery overview ----
# (legend upper-right keeps the seismic row clear; U2 can sit below the
#  point estimate where eps_under < 0 --- bias-corrected bound)
d5 = json.load(open("battery_v5.json"))["domains"]
b5b = {d["title"]: d for d in json.load(open("battery_v5b.json"))}
b5c = {d["title"]: d for d in json.load(open("battery_v5c.json"))}
order = ["Two-state Markov", "i.i.d. null", "LOCATA azimuth", "LOCATA VAD",
         "Sperm-whale codas", "GOES protons", "GOES X-ray flux",
         "GOES magnetometer", "Seismic ANMO"]
v5 = {d["title"]: d for d in d5}
fig, ax = plt.subplots(figsize=(4.9, 2.9))
ys = np.arange(len(order))[::-1]
for y, name in zip(ys, order):
    d = v5[name]
    g = d["max_gain"]
    eo, eu = d["eps_over"], d["eps_under"]
    lo, hi = min(g - eo, g + eu), max(g - eo, g + eu)
    ax.plot([lo, hi], [y, y], color=GREY, lw=3, alpha=0.55, solid_capstyle="butt")
    ax.plot(g + eu, y, marker=".", color=GREY, ms=6, zorder=4)
    ax.plot(g, y, "o", color=BLUE, ms=5, zorder=6)
    if name in b5b:
        ax.plot(b5b[name]["L05"], y + 0.22, marker="|", color=TEAL, ms=7,
                mew=1.8, lw=0, zorder=5)
    if name in b5c:
        ax.plot(b5c[name]["sel_L05"], y - 0.22, marker="|", color=ORANGE, ms=7,
                mew=1.8, lw=0, zorder=5)
ax.axvline(0, color="0.8", lw=0.8)
ax.axvline(0.03, color=RED, lw=1.0, ls=":")
ax.text(0.031, ys[-1] - 0.55, "practical floor", color=RED, fontsize=7, va="bottom")
ax.set_yticks(ys)
ax.set_yticklabels(order)
ax.set_xlabel("history-class gain over exact single-sample value")
ax.set_xlim(-0.085, 0.20)
ax.legend(handles=[
    Line2D([0], [0], marker="o", color=BLUE, lw=0, ms=5, label="gain (point est.)"),
    Line2D([0], [0], color=GREY, lw=3, alpha=0.55,
           label=r"$\hat g-\varepsilon_{\rm over}$ to $U_2=\hat g+\varepsilon_{\rm under}$"),
    Line2D([0], [0], marker="|", color=TEAL, lw=0, ms=7, mew=1.8,
           label=r"$L^{\rm blk}_{D^*}$"),
    Line2D([0], [0], marker="|", color=ORANGE, lw=0, ms=7, mew=1.8,
           label=r"$L^{\rm blk}_{\rm max}$"),
], loc="upper right", framealpha=0.95)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig("fig_battery.pdf")
print("all three figures regenerated")
