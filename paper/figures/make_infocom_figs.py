"""Generate publication-quality INFOCOM figures from committed E8 result JSONs.
Outputs pareto_gpu.{pdf,png} and pareto_cpu.{pdf,png} into this directory."""

import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "benchmarks", "infocom", "out")
T = {3: 3.182}  # t crit, 95%, df=3 (4 reps)


def ci(v):
    n = len(v)
    m = sum(v) / n
    sd = (sum((x - m) ** 2 for x in v) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return m, (T.get(n - 1, 2.0) * sd / n**0.5 if n > 1 else 0.0)


def load(subdir):
    by = {}
    for f in glob.glob(os.path.join(OUT, subdir, "E8_*_r*.json")):
        r = json.load(open(f))["result"]
        d = by.setdefault(r["policy"], {"g": [], "rho": []})
        d["g"].append(r["goodput_tasks_per_s"])
        d["rho"].append(r["monitor"]["cap_violation_fraction"])
    return by


COLORS = {"naive": "#d62728", "aimd": "#2ca02c", "static": "#1f77b4"}
MARK = {"naive": "s", "aimd": "o", "static": "^"}


def pareto(subdir, title, eps, fname):
    by = load(subdir)
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    gmax = 0.0
    for pol in ["naive", "aimd", "static"]:
        gm, gh = ci(by[pol]["g"])
        rm, rh = ci(by[pol]["rho"])
        gmax = max(gmax, gm + gh)
        ax.errorbar(rm, gm, xerr=rh, yerr=gh, fmt=MARK[pol], color=COLORS[pol],
                    capsize=3, ms=7, label=pol, zorder=3)
        # keep labels off the frame: right-side points label leftward
        if rm > 0.6:
            ax.annotate(pol, (rm, gm), textcoords="offset points",
                        xytext=(-9, 5), ha="right", fontsize=9)
        else:
            ax.annotate(pol, (rm, gm), textcoords="offset points",
                        xytext=(9, 5), ha="left", fontsize=9)
    ax.axvline(eps, ls="--", color="grey", lw=1)
    ax.set_xlabel(r"over-budget rate $\rho$  (lower = more polite)")
    ax.set_ylabel("goodput (tasks/s)")
    ax.set_title(title, fontsize=10)
    ax.set_xlim(-0.15, 1.20)       # margins so markers/labels clear the frame
    ax.set_ylim(0, gmax * 1.32)    # headroom above the top point
    ax.text(eps + 0.02, gmax * 0.04, r"$\rho=\epsilon$", color="grey", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"{fname}.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {fname}.pdf/.png from {subdir}")


def phase(fname="feedback_phase"):
    """Feedback-value phase map: Delta = 1/2 exp(-D/tau_c) over the sensing-age x
    coherence-time plane, with the crossover ridge D=tau_c and the two
    pre-registered contention regimes marked (illustrative placement)."""
    import numpy as np

    D = np.linspace(0.0, 30.0, 400)
    tau = np.linspace(0.6, 30.0, 400)
    DD, TT = np.meshgrid(D, tau)
    Z = 0.5 * np.exp(-DD / TT)  # Delta(D) = 1/2 r(D), r(D)=e^{-D/tau_c}

    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    cf = ax.contourf(DD, TT, Z, levels=np.linspace(0, 0.5, 26), cmap="magma")
    # crossover ridge D = tau_c  (Delta = 1/2 e^{-1} ~ 0.184)
    ax.plot(D, D, ls="--", color="white", lw=1.3)
    ax.text(25.0, 27.2, r"$D=\tau_c$", color="white", fontsize=8, rotation=38,
            ha="center", va="center")
    # region descriptors: dark ink on the bright zone, light ink on the dark zone
    ax.text(0.8, 28.8, r"feedback wins ($\tau_c\!\gg\!D$)", color="0.12",
            fontsize=8.5, ha="left", va="center")
    ax.text(29.3, 2.0, r"breaks even ($\tau_c\!\lesssim\!D$)", color="white",
            fontsize=8.5, ha="right", va="center")
    # the two pre-registered experiments (illustrative placement on the map)
    ax.plot(4.0, 22.0, "o", ms=8, mfc="#2ca02c", mec="white", mew=1.2, zorder=5)
    ax.annotate("structured\n(square)", (4.0, 22.0), textcoords="offset points",
                xytext=(9, 0), fontsize=8, color="0.12", va="center")
    ax.plot(11.0, 5.0, "s", ms=8, mfc="#d62728", mec="white", mew=1.2, zorder=5)
    ax.annotate("memoryless\n(Poisson)", (11.0, 5.0), textcoords="offset points",
                xytext=(9, 5), fontsize=8, color="white", va="center")
    ax.set_xlabel(r"sensing age $D$  (epochs)")
    ax.set_ylabel(r"coherence time $\tau_c$  (epochs)")
    ax.set_xlim(0, 30)
    ax.set_ylim(0.6, 30)
    cb = fig.colorbar(cf, ax=ax, ticks=[0, 0.1, 0.2, 0.3, 0.4, 0.5], pad=0.03)
    cb.set_label(r"$\Delta(D)=\frac{1}{2} r(D)$  (value of feedback)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"{fname}.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {fname}.pdf/.png")


phase()  # analytic; no data dependency, so generate first
try:
    pareto("e8_atlas", "End-to-end (GPU pool, C=2)", 0.0, "pareto_gpu")
    pareto("e8_atlas_cpu", "End-to-end (CPU pool, C=8)", 0.0, "pareto_cpu")
except (FileNotFoundError, KeyError) as e:
    print(f"skipped pareto (E8 result JSONs not present here): {e}")
