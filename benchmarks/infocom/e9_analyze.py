"""Aggregate E9 contended-Pareto results and emit summary JSON + LaTeX + figures.

Reads a local dir of e9_contended.py JSON outputs (pulled from Atlas), groups by
(profile, policy) over seeds, computes mean +/- 95% t-CI for goodput and
over-admission rho, competitor throughput retained (impoliteness), and thermal
stats. Writes:
  - e9_summary.json
  - ../../paper/figures/pareto_contended_{square,poisson}.{pdf,png}
  - ../../paper/figures/e9_competitor_harm.{pdf,png}
  - ../../paper/figures/e9_thermal_demo.{pdf,png}   (if thermal trials present)

Usage:  python e9_analyze.py --indir e9_results
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def ci95(xs):
    n = len(xs)
    if n == 0:
        return (float("nan"), 0.0)
    m = sum(xs) / n
    if n < 2:
        return (m, 0.0)
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    t = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57}.get(n, 1.96)
    return (m, t * sd / math.sqrt(n))


def load(indir):
    rows = []
    for f in glob.glob(os.path.join(indir, "*.json")):
        try:
            d = json.load(open(f))
            if d.get("experiment") == "E9":
                rows.append(d)
        except Exception:
            pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="e9_results")
    ap.add_argument("--figdir", default="../../paper/figures")
    a = ap.parse_args()
    rows = load(a.indir)
    print(f"[e9-analyze] loaded {len(rows)} trials")

    # baseline competitor iters per profile (undisturbed = max single competitor)
    base = defaultdict(float)
    for d in rows:
        prof = d["result"]["profile"]
        for it in (d["result"].get("competitor_iters") or []):
            if it:
                base[prof] = max(base[prof], it)

    # group non-thermal trials by (profile, policy)
    grp = defaultdict(lambda: defaultdict(list))
    thermal = []
    for d in rows:
        r = d["result"]
        if r.get("contaminated"):
            print(f"  [discard-contaminated] {r['policy']}/{r['profile']} seed={r['seed']}")
            continue
        if r.get("thermal_on"):
            thermal.append(d)
            continue
        key = (r["profile"], r["policy"])
        grp[key]["goodput"].append(r["goodput_tasks_per_s"])
        grp[key]["rho"].append(r["over_admission_rho"])
        ci = [x for x in (r.get("competitor_iters") or []) if x]
        if ci and base[r["profile"]]:
            grp[key]["comp_ret"].append((sum(ci) / len(ci)) / base[r["profile"]])

    summary = {}
    for (prof, pol), d in sorted(grp.items()):
        g_m, g_e = ci95(d["goodput"])
        r_m, r_e = ci95(d["rho"])
        c_m, _ = ci95(d.get("comp_ret", [float("nan")]))
        summary[f"{prof}/{pol}"] = {
            "n": len(d["goodput"]),
            "goodput": [round(g_m, 4), round(g_e, 4)],
            "rho": [round(r_m, 3), round(r_e, 3)],
            "competitor_retained": round(c_m, 3),
        }
        print(f"  {prof:8s} {pol:6s} n={len(d['goodput'])} "
              f"goodput={g_m:.4f}+-{g_e:.4f} rho={r_m:.3f}+-{r_e:.3f} "
              f"comp_retained={c_m:.2f}")

    # ---- Pareto figures (per profile) -----------------------------------------
    colors = {"naive": "#d62728", "static": "#1f77b4", "aimd": "#2ca02c"}
    for prof in sorted({p for p, _ in grp}):
        fig, ax = plt.subplots(figsize=(3.4, 2.6))
        for pol in ("naive", "static", "aimd"):
            s = summary.get(f"{prof}/{pol}")
            if not s:
                continue
            ax.errorbar(s["rho"][0], s["goodput"][0],
                        xerr=s["rho"][1], yerr=s["goodput"][1],
                        fmt="o", color=colors[pol], capsize=3, ms=7, label=pol)
            ax.annotate(pol, (s["rho"][0], s["goodput"][0]),
                        textcoords="offset points", xytext=(6, 4), fontsize=8)
        ax.set_xlabel(r"over-admission $\rho$ (impoliteness)")
        ax.set_ylabel("goodput (tasks/s)")
        ax.set_xlim(-0.05, 1.0)
        ax.set_title(f"Contended Pareto ({prof})", fontsize=9)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        for ext in ("pdf", "png"):
            fig.savefig(os.path.join(a.figdir, f"pareto_contended_{prof}.{ext}"), dpi=150)
        plt.close(fig)

    # ---- competitor harm bar ---------------------------------------------------
    profs = sorted({p for p, _ in grp})
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    x = range(len(profs)); w = 0.25
    for j, pol in enumerate(("naive", "static", "aimd")):
        vals = [1.0 - summary.get(f"{pr}/{pol}", {}).get("competitor_retained", 1.0)
                for pr in profs]
        ax.bar([i + (j - 1) * w for i in x], vals, w, color=colors[pol], label=pol)
    ax.set_xticks(list(x)); ax.set_xticklabels(profs)
    ax.set_ylabel("competitor throughput lost")
    ax.set_title("Impoliteness: harm to the other tenant", fontsize=9)
    ax.legend(fontsize=7); ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(a.figdir, f"e9_competitor_harm.{ext}"), dpi=150)
    plt.close(fig)

    # ---- thermal demo time series ---------------------------------------------
    if thermal:
        d = thermal[0]
        s = d.get("samples", [])
        ts = [x["t"] for x in s]
        temps = [x["temp"] for x in s]
        caps = [x["cap"] for x in s]
        sp = d["result"].get("setpoint")
        fig, ax = plt.subplots(figsize=(3.4, 2.6))
        ax.plot(ts, temps, color="#d62728", label="GPU temp")
        if sp:
            ax.axhline(sp, ls="--", color="k", lw=1, label=f"setpoint {sp:.0f}")
        ax2 = ax.twinx()
        ax2.step(ts, caps, color="#2ca02c", where="post", alpha=0.6, label="concurrency cap")
        ax.set_xlabel("time (s)"); ax.set_ylabel("GPU temp (C)")
        ax2.set_ylabel("thermal cap")
        ax.set_title("Micro tier: thermal-held burst", fontsize=9)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        for ext in ("pdf", "png"):
            fig.savefig(os.path.join(a.figdir, f"e9_thermal_demo.{ext}"), dpi=150)
        plt.close(fig)
        summary["_thermal"] = [{
            "policy": t["result"]["policy"], "seed": t["result"]["seed"],
            "setpoint": t["result"]["setpoint"], "peak_temp": t["result"]["peak_temp"],
            "mean_temp": t["result"]["mean_temp"],
            "throttle_fraction": t["result"]["thermal_throttle_fraction"],
            "goodput": t["result"]["goodput_tasks_per_s"],
            "rho": t["result"]["over_admission_rho"],
        } for t in thermal]

    json.dump(summary, open("e9_summary.json", "w"), indent=2)
    print("[e9-analyze] wrote e9_summary.json + figures to", a.figdir)


if __name__ == "__main__":
    main()
