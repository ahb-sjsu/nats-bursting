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
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for pol in ["naive", "aimd", "static"]:
        gm, gh = ci(by[pol]["g"])
        rm, rh = ci(by[pol]["rho"])
        ax.errorbar(rm, gm, xerr=rh, yerr=gh, fmt=MARK[pol], color=COLORS[pol],
                    capsize=3, ms=8, label=pol, zorder=3)
        ax.annotate(pol, (rm, gm), textcoords="offset points", xytext=(8, 4), fontsize=9)
    ax.axvline(eps, ls="--", color="grey", lw=1)
    ax.text(eps + 0.01, ax.get_ylim()[0], r"$\rho=\epsilon$", color="grey", fontsize=8)
    ax.set_xlabel(r"over-budget rate $\rho$  (lower = more polite)")
    ax.set_ylabel("goodput (tasks/s)")
    ax.set_title(title, fontsize=10)
    ax.set_xlim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"{fname}.{ext}"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {fname}.pdf/.png from {subdir}")


pareto("e8_atlas", "End-to-end (GPU pool, C=2)", 0.0, "pareto_gpu")
pareto("e8_atlas_cpu", "End-to-end (CPU pool, C=8)", 0.0, "pareto_cpu")
