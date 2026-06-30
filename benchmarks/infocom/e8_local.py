"""Local-process E8 on Atlas GPUs (controlled testbed; no k8s/NATS/image-pull).

Each "job" is a subprocess doing real CUDA matmul for HOLD s on a round-robin GPU
(via CUDA_VISIBLE_DEVICES). The policy controls concurrency with a completion-gated
in-flight limiter (same logic as run.py E8). A monitor thread samples running-process
concurrency. Eliminates the NRP scheduling + cold-image-pull variance that produced
three nulls. One policy per invocation; writes a run.py-E8-compatible JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

BURN = (
    "import time,torch\n"
    "t=time.time()+{hold}\n"
    "x=torch.randn({n},{n},device='cuda')\n"
    "while time.time()<t: x=(x@x).remainder_(7.0).add_(1.0)\n"
    "torch.cuda.synchronize()\n"
)
BURN_CPU = (
    "import time,numpy as np\n"
    "t=time.time()+{hold}\n"
    "a=np.random.rand({n},{n}); x=a\n"
    "while time.time()<t: x=(x@a)%7.0+1.0\n"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--burst", type=int, default=4)
    ap.add_argument("--budget", type=int, default=2)  # C (politeness budget)
    ap.add_argument("--hard-cap", type=int, default=3, dest="hard_cap")
    ap.add_argument("--hold", type=float, default=30.0)
    ap.add_argument("--matmul", type=int, default=4096)
    ap.add_argument("--rate", type=float, default=0.033)  # static submit rate
    ap.add_argument("--gpus", default="1,0")  # round-robin; GPU1 (free) first
    ap.add_argument("--device", default="gpu", choices=["gpu", "cpu"])
    ap.add_argument("--pybin", default=sys.executable)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    gpus = a.gpus.split(",")
    pol = a.baseline
    if pol == "naive":
        window, rate = min(a.burst, a.hard_cap), None
    elif pol == "static":
        window, rate = a.burst, a.rate
    elif pol == "aimd":
        window, rate = a.budget, None
    else:
        raise SystemExit(f"bad policy {pol}")

    procs: list[subprocess.Popen] = []
    launched = [0]
    samples: list[dict] = []
    stop = threading.Event()
    t0 = time.time()

    def in_flight() -> int:
        return sum(1 for p in procs if p.poll() is None)

    def mon() -> None:
        while not stop.is_set():
            samples.append({"t": round(time.time() - t0, 2), "n": in_flight()})
            stop.wait(a.interval)

    mt = threading.Thread(target=mon, daemon=True)
    mt.start()

    loop0 = time.time()
    for i in range(a.burst):
        if rate:
            tgt = loop0 + i / max(rate, 1e-9)
            time.sleep(max(0.0, tgt - time.time()))
        while in_flight() >= window:
            time.sleep(0.2)
        if a.device == "cpu":
            # 1 thread/proc so each worker pegs exactly one core (clean slot accounting)
            env = dict(
                os.environ,
                CUDA_VISIBLE_DEVICES="",
                OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
                NUMEXPR_NUM_THREADS="1",
            )
            code = BURN_CPU.format(hold=a.hold, n=a.matmul)
        else:
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpus[i % len(gpus)])
            code = BURN.format(hold=a.hold, n=a.matmul)
        procs.append(
            subprocess.Popen(
                [a.pybin, "-c", code],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        launched[0] += 1

    for p in procs:
        p.wait()
    wall = time.time() - t0
    stop.set()
    mt.join(timeout=2)

    ns = [s["n"] for s in samples] or [0]
    peak = max(ns)
    capviol = sum(1 for n in ns if n > a.budget) / len(ns)
    completed = sum(1 for p in procs if p.returncode == 0)
    res = {
        "policy": pol,
        "burst": a.burst,
        "completed": completed,
        "burst_completion_s": wall,
        "goodput_tasks_per_s": completed / wall if wall else 0.0,
        "monitor": {
            "peak_concurrency": peak,
            "cap": a.budget,
            "cap_violation_fraction": capviol,
            "util_floor_breach_fraction": None,
            "n_samples": len(ns),
        },
        "over_admission_rho": capviol,
    }
    with open(a.out, "w") as f:
        json.dump(
            {
                "experiment": "E8",
                "cfg": {"kcap": a.budget, "local": True, "gpus": a.gpus},
                "result": res,
            },
            f,
            indent=2,
        )
    print(
        f"[e8_local] {pol} done={completed}/{a.burst} wall={wall:.1f}s "
        f"peak={peak} over_budget={capviol:.2f} goodput={completed/wall:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
