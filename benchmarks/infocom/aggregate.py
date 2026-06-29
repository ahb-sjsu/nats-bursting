"""Aggregate E8 + baseline runs into the goodput-rho Pareto and the
rho_obs-vs-rho_pred money plot.

Consumes one JSON per run (multiple per label = repeats -> mean +/- 95% CI):
  * baselines.py outputs  : label=backend; goodput=goodput_tasks_per_s;
    rho=metrics.cap_violation_fraction (or util_floor_breach_fraction with
    --rho-metric util); completion=burst_completion_s; peak=metrics.peak_concurrency.
  * run.py E8 outputs     : label=result.policy; completion=result.burst_completion_s;
    goodput=result.completed/completion; rho from result['over_admission_rho'] or a
    result['monitor'] block. If neither is present rho is None and the run is listed
    but kept off the Pareto (flagged) -- run.py E8 must be run under monitoring to
    populate rho (shared Monitor from baselines.py / monitor wiring).

Outputs: pareto.png + money.png (if matplotlib), data.csv, SUMMARY.md.
The money plot needs the measured detection delay D (--D, epochs) and, per aimd
record, alpha/beta (from cfg) and mean available capacity abar (--abar or the mean
a_target from a --contention jsonl): rho_pred = D*alpha / ((1-beta)*abar).
"""

from __future__ import annotations

import argparse
import csv
import glob as _glob
import json
import math
import os

_T95 = {
    1: 12.71,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
}


def mean_ci(vals: list[float]) -> tuple[float, float]:
    xs = [v for v in vals if v is not None]
    n = len(xs)
    if n == 0:
        return float("nan"), 0.0
    m = sum(xs) / n
    if n == 1:
        return m, 0.0
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    return m, _T95.get(n - 1, 1.96) * sd / math.sqrt(n)


def normalize(rec: dict, rho_metric: str) -> dict | None:
    """Map a baselines.py or run.py-E8 record to a common row, or None if unusable."""
    if "metrics" in rec and "backend" in rec:  # baselines.py
        m = rec["metrics"]
        rho = (
            m.get("util_floor_breach_fraction")
            if rho_metric == "util"
            else m.get("cap_violation_fraction")
        )
        return {
            "label": rec["backend"],
            "source": "baseline",
            "goodput": rec.get("goodput_tasks_per_s"),
            "rho": rho,
            "completion": rec.get("burst_completion_s"),
            "peak": m.get("peak_concurrency"),
            "cap": m.get("cap"),
            "cfg": {},
        }
    if rec.get("experiment") == "E8":  # run.py E8
        r = rec.get("result", {})
        comp = r.get("burst_completion_s")
        good = r.get("completed") / comp if comp and r.get("completed") else None
        mon = r.get("monitor", {})
        rho = r.get("over_admission_rho", mon.get("cap_violation_fraction"))
        return {
            "label": r.get("policy", "e8"),
            "source": "e8",
            "goodput": good,
            "rho": rho,
            "completion": comp,
            "peak": mon.get("peak_concurrency"),
            "cap": rec.get("cfg", {}).get("kcap"),
            "cfg": rec.get("cfg", {}) | {k: r.get(k) for k in ("alpha", "beta")},
        }
    return None


def group(rows: list[dict]) -> dict[str, dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["label"], []).append(r)
    out = {}
    for label, rs in by.items():
        gm, gh = mean_ci([r["goodput"] for r in rs])
        rm, rh = mean_ci([r["rho"] for r in rs])
        cm, ch = mean_ci([r["completion"] for r in rs])
        out[label] = {
            "n": len(rs),
            "source": rs[0]["source"],
            "goodput": (gm, gh),
            "rho": (rm, rh),
            "completion": (cm, ch),
            "peak": max((r["peak"] or 0) for r in rs),
            "cap": rs[0]["cap"],
            "rho_available": any(r["rho"] is not None for r in rs),
            "runs": rs,
        }
    return out


def abar_from_contention(path: str | None) -> float | None:
    if not path:
        return None
    vals = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            vals.append(json.loads(line).get("a_target"))
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--glob", default="out/*.json", help="result JSONs (E8 + baselines)"
    )
    ap.add_argument(
        "--rho-metric", choices=["cap", "util"], default="cap", dest="rho_metric"
    )
    ap.add_argument(
        "--eps", type=float, default=0.1, help="policy feasibility line rho<=eps"
    )
    ap.add_argument(
        "--D", type=float, default=None, help="detection delay (epochs) for money plot"
    )
    ap.add_argument("--abar", type=float, default=None, help="mean available capacity")
    ap.add_argument(
        "--contention", default=None, help="contention jsonl -> mean a_target = abar"
    )
    ap.add_argument("--out-dir", default="out/agg", dest="out_dir")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    rows = []
    for p in _glob.glob(a.glob):
        try:
            r = normalize(json.load(open(p, encoding="utf-8")), a.rho_metric)
        except Exception:
            r = None
        if r:
            r["_file"] = os.path.basename(p)
            rows.append(r)
    if not rows:
        raise SystemExit(f"no usable records matched {a.glob}")
    g = group(rows)
    abar = a.abar if a.abar is not None else abar_from_contention(a.contention)

    # ---- CSV (per run) ----
    with open(f"{a.out_dir}/data.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["file", "label", "source", "goodput", "rho", "completion_s", "peak", "cap"]
        )
        for r in rows:
            w.writerow(
                [
                    r["_file"],
                    r["label"],
                    r["source"],
                    r["goodput"],
                    r["rho"],
                    r["completion"],
                    r["peak"],
                    r["cap"],
                ]
            )

    # ---- SUMMARY.md ----
    lines = [
        "# E8 + baselines summary\n",
        f"rho metric: `{a.rho_metric}`; feasibility eps = {a.eps}; "
        f"abar = {abar if abar is not None else 'n/a'}.\n",
        "| label | src | n | goodput (mean±CI) | rho (mean±CI) | completion s | peak/cap |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, s in sorted(
        g.items(),
        key=lambda kv: (kv[1]["rho"][0] if not math.isnan(kv[1]["rho"][0]) else 9),
    ):
        rho = (
            "n/a (needs monitoring)"
            if not s["rho_available"]
            else f"{s['rho'][0]:.3f}±{s['rho'][1]:.3f}"
        )
        lines.append(
            f"| {label} | {s['source']} | {s['n']} | {s['goodput'][0]:.2f}±{s['goodput'][1]:.2f} "
            f"| {rho} | {s['completion'][0]:.1f}±{s['completion'][1]:.1f} | {s['peak']}/{s['cap']} |"
        )
    open(f"{a.out_dir}/SUMMARY.md", "w", encoding="utf-8").write(
        "\n".join(lines) + "\n"
    )

    # ---- plots ----
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print(
            f"[aggregate] matplotlib unavailable; wrote data.csv + SUMMARY.md to {a.out_dir}"
        )
        return

    # Pareto: goodput (y) vs rho (x); upper-left is best; eps line.
    fig, ax = plt.subplots(figsize=(6, 4.2))
    for label, s in g.items():
        if not s["rho_available"] or math.isnan(s["goodput"][0]):
            continue
        ax.errorbar(
            s["rho"][0],
            s["goodput"][0],
            xerr=s["rho"][1],
            yerr=s["goodput"][1],
            fmt="o",
            capsize=3,
            label=label,
        )
        ax.annotate(
            label,
            (s["rho"][0], s["goodput"][0]),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=9,
        )
    ax.axvline(a.eps, ls="--", color="grey", lw=1)
    ax.text(
        a.eps, ax.get_ylim()[1], f" rho=eps={a.eps}", color="grey", va="top", fontsize=8
    )
    ax.set_xlabel("over-admission rate rho (lower = more polite)")
    ax.set_ylabel("goodput (tasks/s, higher = better)")
    ax.set_title("Goodput vs policy compliance")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(f"{a.out_dir}/pareto.png", dpi=150)
    plt.close(fig)

    # Money plot: rho_obs vs rho_pred for aimd runs.
    if a.D is not None and abar:
        pts = []
        for r in rows:
            if r["label"] == "aimd" and r["rho"] is not None:
                al, be = r["cfg"].get("alpha"), r["cfg"].get("beta")
                if al and be is not None:
                    pts.append((a.D * al / ((1 - be) * abar), r["rho"]))
        if pts:
            fig, ax = plt.subplots(figsize=(4.6, 4.4))
            xs, ys = zip(*pts)
            lim = max(max(xs), max(ys)) * 1.15 + 1e-6
            ax.plot([0, lim], [0, lim], ls="--", color="grey", lw=1, label="y=x")
            ax.scatter(xs, ys, color="C3", zorder=3)
            ax.set_xlabel("rho_pred  (Prop. 2:  D*alpha/((1-beta)*abar))")
            ax.set_ylabel("rho_obs  (measured)")
            ax.set_title("AIMD: predicted vs measured over-admission")
            ax.legend(fontsize=8)
            fig.tight_layout()
            fig.savefig(f"{a.out_dir}/money.png", dpi=150)
            plt.close(fig)
            print(f"[aggregate] money plot: {len(pts)} aimd point(s)")
        else:
            print("[aggregate] no aimd records with alpha/beta+rho; skipped money plot")
    else:
        print("[aggregate] money plot skipped (need --D and --abar/--contention)")

    print(f"[aggregate] wrote pareto.png + SUMMARY.md + data.csv to {a.out_dir}")


if __name__ == "__main__":
    main()
