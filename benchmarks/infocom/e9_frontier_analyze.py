"""Aggregate E9-F frontier trials into the live matched-mismatch comparison.

Groups /tmp/e9/frontier/*.json by cell, computes mean +/- 95% t-CI of goodput
and rho, builds the record-independent frontier as the CONCAVE UPPER ENVELOPE
of the static cells plus the origin (time-sharing between record-independent
policies is itself record-independent, so the envelope is achievable), then
evaluates each AIMD cell against the envelope at its own mean rho:

    Delta_live(cell) = g_aimd - g_static_envelope(rho_aimd)

Writes frontier_summary.json and a text table. Stdlib only.

Usage:  python3 e9_frontier_analyze.py [--indir /tmp/e9/frontier]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from collections import defaultdict


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


def concave_envelope(pts):
    """Upper concave hull of (rho, g) points including the origin."""
    pts = sorted(set([(0.0, 0.0)] + pts))
    hull = []
    for p in pts:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            if (y2 - y1) * (p[0] - x1) <= (p[1] - y1) * (x2 - x1):
                hull.pop()
            else:
                break
        hull.append(p)
    return hull


def env_eval(hull, x):
    if x <= hull[0][0]:
        return hull[0][1]
    for (x1, y1), (x2, y2) in zip(hull, hull[1:]):
        if x1 <= x <= x2:
            w = 0.0 if x2 == x1 else (x - x1) / (x2 - x1)
            return y1 + w * (y2 - y1)
    return hull[-1][1]  # beyond last point: envelope is flat (stop admitting more)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="/tmp/e9/frontier")
    a = ap.parse_args()

    cells = defaultdict(list)
    for f in glob.glob(os.path.join(a.indir, "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        r = d.get("result", {})
        if d.get("experiment") != "E9" or r.get("contaminated"):
            continue
        base = os.path.basename(f).rsplit("_", 1)[0]
        cells[base].append((r["over_admission_rho"], r["goodput_tasks_per_s"]))

    summary = {"cells": {}, "static_envelope": [], "matched": []}
    static_pts = []
    for tag in sorted(cells):
        rhos, gs = zip(*cells[tag])
        (rm, rc), (gm, gc) = ci95(list(rhos)), ci95(list(gs))
        summary["cells"][tag] = {"n": len(gs), "rho": rm, "rho_ci": rc,
                                 "g": gm, "g_ci": gc}
        if tag.startswith("static"):
            static_pts.append((rm, gm))

    hull = concave_envelope(static_pts)
    summary["static_envelope"] = hull

    print(f"{'cell':24s} {'n':>2s} {'rho':>6s} {'g':>7s} {'env(rho)':>8s} "
          f"{'Delta':>7s} {'ratio':>6s}")
    for tag in sorted(cells):
        c = summary["cells"][tag]
        if tag.startswith("aimd"):
            ge = env_eval(hull, c["rho"])
            delta, ratio = c["g"] - ge, (c["g"] / ge if ge > 0 else float("inf"))
            summary["matched"].append(
                {"cell": tag, "rho": c["rho"], "g": c["g"], "g_ci": c["g_ci"],
                 "static_env": ge, "delta": delta, "ratio": ratio})
            print(f"{tag:24s} {c['n']:2d} {c['rho']:6.3f} {c['g']:7.4f} "
                  f"{ge:8.4f} {delta:+7.4f} {ratio:6.2f}")
        else:
            print(f"{tag:24s} {c['n']:2d} {c['rho']:6.3f} {c['g']:7.4f}")

    out = os.path.join(a.indir, "frontier_summary.json")
    json.dump(summary, open(out, "w"), indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
