"""Validate the regime-adaptive controller against the feedback-usefulness law on
LIVE (Atlas GPU) markov-profile results.

Law (INFOCOM):  Delta(D) = 1/2 * r(D),  r(D) = corr(a_t, a_{t-D}) = (1-2p)^D.

The live campaign sweeps the true flip rate p at fixed sensing age D and runs three
controllers per p: static (safe floor), aimd (always closed-loop), adaptive (estimate
r_hat online, run AIMD iff r_hat > gamma else fall back to static). This checks:

  (1) the ONLINE estimator lands on the curve: r_hat ~= r_true = (1-2p)^D;
  (2) the regime switch is correct: frac_closed_loop ~ 1 when r_true > gamma, ~0 below;
  (3) the behavioural payoff: adaptive goodput ~= best of {aimd, static} at each p.

Writes ../../paper/figures/e9_adaptive_curve.{pdf,png} and prints a verdict.

Usage:  python e9_adaptive_curve.py --indir e9_results
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def load_markov(indir):
    by = defaultdict(lambda: defaultdict(list))  # by[p][policy] -> list of result dicts
    D = gamma = None
    for f in glob.glob(os.path.join(indir, "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        r = d.get("result", {})
        if r.get("profile") != "markov" or r.get("contaminated"):
            continue
        p = d["cfg"]["p_flip"]
        by[p][r["policy"]].append(d)
        if r.get("adaptive"):
            D = r["adaptive"]["D"]
            gamma = r["adaptive"]["gamma"]
    return by, D, gamma


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="e9_results")
    ap.add_argument("--figdir", default="../../paper/figures")
    a = ap.parse_args()

    by, D, gamma = load_markov(a.indir)
    ps = sorted(by)
    print(f"[curve] D={D} gamma={gamma}  p_flip points: {ps}\n")

    rows = []
    print(f"{'p':>5} {'r_true':>7} {'½r(D)':>7} {'r_hat':>7} {'|err|':>6} "
          f"{'closed':>6} {'g_stat':>7} {'g_aimd':>7} {'g_adap':>7} {'best':>5}")
    for p in ps:
        r_true = (1 - 2 * min(p, 0.5)) ** D
        half = 0.5 * r_true
        adap = [d["result"] for d in by[p].get("adaptive", [])]
        r_hat = mean([x["adaptive"]["r_hat"] for x in adap])
        closed = mean([x["adaptive"]["frac_closed_loop"] for x in adap])
        g = {pol: mean([d["result"]["goodput_tasks_per_s"] for d in by[p].get(pol, [])])
             for pol in ("static", "aimd", "adaptive")}
        # which fixed policy is best at this p — adaptive should match it
        best = "aimd" if g["aimd"] >= g["static"] else "static"
        adap_vs_best = g["adaptive"] / max(g[best], 1e-9)
        rows.append(dict(p=p, r_true=r_true, half=half, r_hat=r_hat, closed=closed,
                         g=g, best=best, adap_vs_best=adap_vs_best))
        print(f"{p:>5} {r_true:>7.3f} {half:>7.3f} {r_hat:>7.3f} "
              f"{abs(r_hat - r_true):>6.3f} {closed:>6.2f} "
              f"{g['static']:>7.4f} {g['aimd']:>7.4f} {g['adaptive']:>7.4f} {best:>5}")

    # ---- verdict ------------------------------------------------------------------
    est_err = mean([abs(r["r_hat"] - r["r_true"]) for r in rows])
    switch_ok = all((r["closed"] > 0.5) == (r["r_true"] > gamma) for r in rows)
    track_ok = all(r["adap_vs_best"] > 0.9 for r in rows)
    print(f"\n[verdict] mean |r_hat - r_true| = {est_err:.3f}  (estimator on-curve)")
    print(f"[verdict] regime switch matches r_true><gamma at every p: {switch_ok}")
    print(f"[verdict] adaptive >= 0.9x best fixed policy at every p:   {track_ok}")

    # ---- figure -------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.7))
    pg = np.linspace(0, 0.5, 200)
    ax1.plot(pg, (1 - 2 * pg) ** D, "k-", lw=1.4, label=r"$r(D)=(1-2p)^D$")
    ax1.plot(pg, 0.5 * (1 - 2 * pg) ** D, "k--", lw=1.2, label=r"$\frac{1}{2}r(D)$")
    ax1.scatter([r["p"] for r in rows], [r["r_hat"] for r in rows],
                c="#d62728", zorder=5, s=42, label=r"live $\hat r$ (online)")
    ax1.axhline(gamma, color="#888", ls=":", lw=1, label=rf"$\gamma={gamma}$")
    ax1.set_xlabel("true flip rate $p$")
    ax1.set_ylabel(r"autocorrelation $r(D)$")
    ax1.set_title(f"Online estimate on the curve (D={D})", fontsize=9)
    ax1.legend(fontsize=6.5, loc="upper right")
    ax1.grid(True, alpha=0.3)

    xs = range(len(rows))
    for pol, c in (("static", "#1f77b4"), ("aimd", "#2ca02c"), ("adaptive", "#d62728")):
        ax2.plot(list(xs), [r["g"][pol] for r in rows], "o-", color=c, ms=5, label=pol)
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([f"{r['p']}\nr={r['r_true']:.2f}" for r in rows], fontsize=6.5)
    ax2.set_xlabel("flip rate $p$ (→ less trackable)")
    ax2.set_ylabel("goodput (tasks/s)")
    ax2.set_title("Adaptive = best-of-both", fontsize=9)
    ax2.legend(fontsize=7)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    os.makedirs(a.figdir, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.figdir, f"e9_adaptive_curve.{ext}"), dpi=150)
    plt.close(fig)
    print(f"[curve] wrote {a.figdir}/e9_adaptive_curve.(pdf|png)")


if __name__ == "__main__":
    main()
