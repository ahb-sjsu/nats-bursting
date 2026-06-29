"""Multi-seed repeats of E1/E3/E5 for confidence intervals.

Network/timing variance (not a PRNG seed) is the thing we're sampling, so each
"seed" is an independent temporal repeat. Reports mean +/- 95% CI (t-based,
df=reps-1) across repeats. Run from this directory, with a responder live on the
far side for E1/E5.

    python multiseed.py --url nats://100.68.134.21:4222 --reps 5 --out out/ms
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os

import numpy as np
import nats

import harness as H

# two-tailed t critical values at 95% by degrees of freedom (reps-1)
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
    a = np.asarray(vals, float)
    n = len(a)
    if n < 2:
        return float(a.mean()) if n else float("nan"), 0.0
    sd = a.std(ddof=1)
    t = _T95.get(n - 1, 1.96)
    return float(a.mean()), float(t * sd / math.sqrt(n))


async def _del_stream(url: str, name: str = "INFOCOM") -> None:
    nc = await nats.connect(url)
    try:
        await nc.jetstream().delete_stream(name)
    except Exception:
        pass
    await nc.drain()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--n-js", type=int, default=150, dest="n_js")
    ap.add_argument("--out", default="out/ms")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    windows = [1, 4, 8, 16, 32]
    runs: dict = {
        "meta": {"reps": a.reps, "n": a.n, "n_js": a.n_js, "url": a.url},
        "E1": [],
        "E3_durable": [],
        "E3_nondurable": [],
        "E5": [],
    }

    print(f"[multiseed] {a.reps} reps", flush=True)
    for i in range(a.reps):
        c = H.Cfg(url=a.url, transport="core", path="tailscale", n=a.n, concurrency=16)
        runs["E1"].append(
            {"rtt": await H.measure_rtt(c), "tp": await H.measure_throughput(c)}
        )
        print(f"  E1 rep {i+1}/{a.reps}", flush=True)
    for storage, key in [
        ("js-durable", "E3_durable"),
        ("js-nondurable", "E3_nondurable"),
    ]:
        for i in range(a.reps):
            await _del_stream(a.url)
            runs[key].append(
                await H.measure_js_publish(
                    H.Cfg(url=a.url, transport=storage, n=a.n_js)
                )
            )
            print(f"  {key} rep {i+1}/{a.reps}", flush=True)
        await _del_stream(a.url)
    for i in range(a.reps):
        sweep = []
        for w in windows:
            tp = await H.measure_throughput(
                H.Cfg(
                    url=a.url, transport="core", path="tailscale", n=a.n, concurrency=w
                )
            )
            tp["window"] = w
            sweep.append(tp)
        runs["E5"].append(sweep)
        print(f"  E5 rep {i+1}/{a.reps}", flush=True)

    with open(f"{a.out}/raw.json", "w") as f:
        json.dump(runs, f, indent=2, default=str)

    # ---- aggregate -> markdown ----
    out = [
        f"# E1/E3/E5 multi-seed results (reps={a.reps}, mean +/- 95% CI)\n",
        f"Independent temporal repeats over tailscale; n={a.n} (E1/E5), n={a.n_js} (E3). "
        "95% CI is t-based across repeats.\n",
    ]

    def agg(key, field_path):
        vals = []
        for rep in runs[key]:
            d = rep
            for k in field_path:
                d = d[k]
            vals.append(d)
        return mean_ci(vals)

    out.append("## E1 — RTT & throughput (tailscale)\n")
    out.append("| metric | mean +/- 95% CI |")
    out.append("|---|---|")
    for label, fp in [
        ("RTT p50 (ms)", ["rtt", "p50_ms"]),
        ("RTT p95 (ms)", ["rtt", "p95_ms"]),
        ("RTT p99 (ms)", ["rtt", "p99_ms"]),
        ("RTT mean (ms)", ["rtt", "mean_ms"]),
        ("throughput (msg/s)", ["tp", "throughput_msgs_s"]),
    ]:
        m, h = agg("E1", fp)
        out.append(f"| {label} | {m:.1f} +/- {h:.1f} |")

    out.append("\n## E3 — JetStream publish->ack (durable vs non-durable)\n")
    out.append("| storage | ack p50 (ms) | ack p95 (ms) | ack p99 (ms) |")
    out.append("|---|---|---|---|")
    for key, lbl in [
        ("E3_durable", "durable (file)"),
        ("E3_nondurable", "non-durable (mem)"),
    ]:
        cells = []
        for f in ["p50_ms", "p95_ms", "p99_ms"]:
            m, h = mean_ci([rep[f] for rep in runs[key]])
            cells.append(f"{m:.1f} +/- {h:.1f}")
        out.append(f"| {lbl} | " + " | ".join(cells) + " |")

    out.append("\n## E5 — concurrency scaling (tailscale)\n")
    out.append("| window | throughput (msg/s) | p99 (ms) |")
    out.append("|---|---|---|")
    for wi, w in enumerate(windows):
        thr = mean_ci([rep[wi]["throughput_msgs_s"] for rep in runs["E5"]])
        p99 = mean_ci([rep[wi]["p99_ms"] for rep in runs["E5"]])
        out.append(
            f"| {w} | {thr[0]:.0f} +/- {thr[1]:.0f} | {p99[0]:.0f} +/- {p99[1]:.0f} |"
        )

    with open(f"{a.out}/RESULTS_MULTISEED.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"[multiseed] wrote {a.out}/RESULTS_MULTISEED.md and raw.json")


if __name__ == "__main__":
    asyncio.run(main())
