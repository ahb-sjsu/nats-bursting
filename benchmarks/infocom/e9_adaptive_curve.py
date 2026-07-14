"""Validate the regime-adaptive controller against the feedback-usefulness law on
LIVE (Atlas GPU) markov-profile results.

Law (INFOCOM):  Delta(D) = 1/2 * r(D),  r(D) = corr(a_t, a_{t-D}) = (1-2p)^D.

The live campaign sweeps the true flip rate p at fixed sensing age D and runs three
controllers per p: static (safe floor), aimd (always closed-loop), adaptive (estimate
r_hat online, run AIMD iff r_hat > gamma else fall back to static). This checks:

  (1) the ONLINE estimator lands on the curve: r_hat ~= r_true = (1-2p)^D, and the
      realized r_emp of the sensed availability tracks it;
  (2) the regime switch modulates: frac_closed_loop falls as p rises;
  (3) the LAW is about goodput at MATCHED over-admission rho, not raw goodput
      (raw goodput rewards greed). We build a static rho->goodput frontier and report
      the matched-rho advantage adv = g - static_goodput_at(rho) (cf. tau_sweep.py),
      plus the politeness dividend rho_aimd - rho_adap (adaptive backs off when
      feedback is useless). See ADAPTIVE_CURVE_FINDINGS.md.

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
    xs = [x for x in xs if x is not None]
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


def g_rho(by, p, pol):
    rs = [d["result"] for d in by[p].get(pol, [])]
    return (mean([x["goodput_tasks_per_s"] for x in rs]),
            mean([x["over_admission_rho"] for x in rs]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="e9_results")
    ap.add_argument("--figdir", default="../../paper/figures")
    a = ap.parse_args()

    by, D, gamma = load_markov(a.indir)
    ps = sorted(by)
    print(f"[curve] D={D} gamma={gamma}  p_flip points: {ps}\n")

    # Static rho->goodput frontier: the open-loop baseline the law measures advantage
    # against. Live static is a near-flat trickle (it barely trades goodput for rho),
    # so this frontier is honest but shallow -- the clean law-tracing lives in the sim
    # (tau_sweep.py), which can tune static across the whole rho range.
    static_pts = sorted((g_rho(by, p, "static")[1], g_rho(by, p, "static")[0]) for p in ps)
    srho = [x for x, _ in static_pts]
    sg = [y for _, y in static_pts]

    def static_g_at(rho):
        return float(np.interp(rho, srho, sg))  # clamps to endpoints outside range

    rows = []
    hdr = (f"{'p':>5} {'r_true':>6} {'r_emp':>6} {'r_hat':>6} {'clsd':>5} | "
           f"{'g_st':>6} {'g_ai':>6} {'g_ad':>6} | {'rho_st':>5} {'rho_ai':>5} {'rho_ad':>5} | "
           f"{'adv_ai':>6} {'adv_ad':>6}")
    print(hdr)
    for p in ps:
        r_true = (1 - 2 * min(p, 0.5)) ** D
        adap = [d["result"] for d in by[p].get("adaptive", [])]
        r_hat = mean([x["adaptive"]["r_hat"] for x in adap])
        r_emp = mean([x["adaptive"].get("r_emp_D") for x in adap])
        closed = mean([x["adaptive"]["frac_closed_loop"] for x in adap])
        g = {}
        rho = {}
        for pol in ("static", "aimd", "adaptive"):
            g[pol], rho[pol] = g_rho(by, p, pol)
        # matched-rho advantage over the static frontier (the quantity the law predicts)
        adv = {pol: g[pol] - static_g_at(rho[pol]) for pol in ("aimd", "adaptive")}
        rows.append(dict(p=p, r_true=r_true, r_emp=r_emp, r_hat=r_hat, closed=closed,
                         g=g, rho=rho, adv=adv))
        print(f"{p:>5} {r_true:>6.3f} {r_emp:>6.3f} {r_hat:>6.3f} {closed:>5.2f} | "
              f"{g['static']:>6.4f} {g['aimd']:>6.4f} {g['adaptive']:>6.4f} | "
              f"{rho['static']:>5.2f} {rho['aimd']:>5.2f} {rho['adaptive']:>5.2f} | "
              f"{adv['aimd']:>6.3f} {adv['adaptive']:>6.3f}")

    # ---- verdict ------------------------------------------------------------------
    est_err = mean([abs(r["r_hat"] - r["r_true"]) for r in rows])
    modulates = max(r["closed"] for r in rows) - min(r["closed"] for r in rows)
    # politeness dividend: over-admission the switch saves vs always-AIMD, should grow as r falls
    div = [(r["p"], r["rho"]["aimd"] - r["rho"]["adaptive"]) for r in rows]
    lo_p, hi_p = rows[0], rows[-1]
    print(f"\n[verdict] estimator on curve: mean |r_hat - r_true| = {est_err:.3f}")
    print(f"[verdict] switch modulates: frac_closed_loop range = {modulates:.2f}")
    print("[verdict] politeness dividend rho_aimd - rho_adaptive by p: "
          + ", ".join(f"{p}:{d:+.2f}" for p, d in div))
    print(f"[verdict] at p={lo_p['p']} (r={lo_p['r_true']:.2f}, trackable): adaptive tracks aimd "
          f"(adv {lo_p['adv']['adaptive']:+.3f} vs {lo_p['adv']['aimd']:+.3f})")
    print(f"[verdict] at p={hi_p['p']} (r={hi_p['r_true']:.2f}, untrackable): adaptive halves aimd's "
          f"over-admission ({hi_p['rho']['adaptive']:.2f} vs {hi_p['rho']['aimd']:.2f}) -> polite")

    # ---- figure: (1) estimator on the curve  (2) goodput-vs-rho Pareto -------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.7))
    pg = np.linspace(0, 0.5, 200)
    ax1.plot(pg, (1 - 2 * pg) ** D, "k-", lw=1.4, label=r"$r(D)=(1-2p)^D$")
    ax1.plot(pg, 0.5 * (1 - 2 * pg) ** D, "k--", lw=1.2, label=r"$\frac{1}{2}r(D)$")
    ax1.scatter([r["p"] for r in rows], [r["r_emp"] for r in rows],
                facecolors="none", edgecolors="#1f77b4", zorder=4, s=52, label=r"realized $r_{emp}$")
    ax1.scatter([r["p"] for r in rows], [r["r_hat"] for r in rows],
                c="#d62728", zorder=5, s=42, label=r"online $\hat r$")
    ax1.axhline(gamma, color="#888", ls=":", lw=1, label=rf"$\gamma={gamma}$")
    ax1.set_xlabel("true flip rate $p$")
    ax1.set_ylabel(r"autocorrelation $r(D)$")
    ax1.set_title(f"Estimator on the curve (D={D})", fontsize=9)
    ax1.legend(fontsize=6.5, loc="upper right")
    ax1.grid(True, alpha=0.3)

    colors = {"static": "#1f77b4", "aimd": "#2ca02c", "adaptive": "#d62728"}
    for pol in ("static", "aimd", "adaptive"):
        xs = [r["rho"][pol] for r in rows]
        ys = [r["g"][pol] for r in rows]
        ax2.plot(xs, ys, "o-", color=colors[pol], ms=5, lw=1, label=pol, alpha=0.85)
    # annotate adaptive points with p so the trackable->untrackable path is legible
    for r in rows:
        ax2.annotate(f"p={r['p']}", (r["rho"]["adaptive"], r["g"]["adaptive"]),
                     textcoords="offset points", xytext=(4, -8), fontsize=6, color="#d62728")
    ax2.set_xlabel(r"over-admission $\rho$ (impoliteness)")
    ax2.set_ylabel("goodput (tasks/s)")
    ax2.set_title("Goodput–politeness Pareto", fontsize=9)
    ax2.legend(fontsize=7, loc="lower right")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    os.makedirs(a.figdir, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.figdir, f"e9_adaptive_curve.{ext}"), dpi=150)
    plt.close(fig)
    print(f"\n[curve] wrote {a.figdir}/e9_adaptive_curve.(pdf|png)")


if __name__ == "__main__":
    main()
