"""funcX (Globus Compute) / Parsl / Ray-style baselines for the E8 comparison.

These frameworks have **no admission controller**: they scale workers to demand.
So the fair comparison is to push the *same* burst of B GPU tasks through each and
measure the *same externally-observable* policy metrics with a shared monitor --
peak concurrent pods vs the cap K, util-floor breaches, and burst-completion --
so every system (naive / static / aimd from run.py E8, plus parsl / globus) lands
on one goodput--rho Pareto. The hypothesis: demand-scaling frameworks achieve
completion by **violating** the pod cap / utilization floor under contention,
which is exactly what the politeness controller avoids.

Backends:
  local  : ProcessPool dry-run (runnable here; concurrency from the pool).
  parsl  : Parsl HighThroughputExecutor (configure a KubernetesProvider so workers
           are pods in the experiment namespace; the config is the bind point).
  globus : Globus Compute (formerly funcX); submit to a configured endpoint whose
           provider launches pods in the namespace (endpoint_id is the bind point).

For parsl/globus the monitor counts pods in the namespace via kubectl, so the
metrics are framework-agnostic. GPU-utilisation (the 40% floor) requires cluster
GPU metrics (DCGM/Prometheus); the `--util-cmd` hook is where that plugs in, and
without it only the concurrency/cap-violation side of rho is reported (stated honestly).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed


def gpu_task(hold_sec: float = 8.0, size: int = 4096) -> str:
    """Real work unit shipped to workers (no sleep). Torch matmul on GPU; numpy
    CPU fallback for the local dry-run."""
    import time as _t

    try:
        import torch

        t = _t.time() + hold_sec
        x = torch.randn(size, size, device="cuda")
        while _t.time() < t:
            x = (x @ x).remainder_(7.0).add_(1.0)
        torch.cuda.synchronize()
        return "gpu"
    except Exception:
        import numpy as np

        t = _t.time() + hold_sec
        a = np.random.rand(256, 256)
        x = a
        while _t.time() < t:
            x = (x @ a) % 7.0 + 1.0
        return "cpu"


class Monitor(threading.Thread):
    """Samples running concurrency (and optional GPU util) every `interval` s."""

    def __init__(self, count_fn, kcap: int, interval: float = 1.0, util_fn=None):
        super().__init__(daemon=True)
        self.count_fn, self.kcap, self.interval, self.util_fn = (
            count_fn,
            kcap,
            interval,
            util_fn,
        )
        self._ev = threading.Event()  # not _stop: Thread._stop is an internal method
        self.samples: list[dict] = []
        self.t0 = time.time()

    def run(self) -> None:
        while not self._ev.is_set():
            u = self.util_fn() if self.util_fn else None
            self.samples.append(
                {"t": round(time.time() - self.t0, 3), "n": self.count_fn(), "util": u}
            )
            self._ev.wait(self.interval)

    def stop(self) -> None:
        self._ev.set()
        self.join(timeout=3)

    def metrics(self) -> dict:
        ns = [s["n"] for s in self.samples] or [0]
        utils = [s["util"] for s in self.samples if s["util"] is not None]
        return {
            "peak_concurrency": max(ns),
            "cap": self.kcap,
            "cap_violation_fraction": sum(1 for n in ns if n > self.kcap) / len(ns),
            "util_floor_breach_fraction": (
                sum(1 for u in utils if u < 0.40) / len(utils) if utils else None
            ),
            "n_samples": len(ns),
        }


def kubectl_pod_counter(ns: str, label: str | None = None):
    sel = ["-l", label] if label else []

    def _c() -> int:
        r = subprocess.run(
            [
                "kubectl",
                "-n",
                ns,
                "get",
                "pods",
                *sel,
                "--field-selector=status.phase=Running",
                "-o",
                "name",
            ],
            capture_output=True,
            text=True,
        )
        return len([x for x in r.stdout.splitlines() if x.strip()])

    return _c


def util_from_cmd(cmd: str | None):
    """Pluggable GPU-util source (e.g. a DCGM/Prometheus query) returning a 0..1
    float on stdout. Returns None if no command given."""
    if not cmd:
        return None

    def _u():
        try:
            out = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=5
            )
            return float(out.stdout.strip())
        except Exception:
            return None

    return _u


def _record(
    out: str, backend: str, B: int, completion: float, first: float | None, mon: Monitor
) -> dict:
    rec = {
        "backend": backend,
        "burst": B,
        "burst_completion_s": completion,
        "submit_to_first_s": first,
        "metrics": mon.metrics(),
        "samples": mon.samples,
        "goodput_tasks_per_s": (B / completion if completion else 0.0),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    return rec


# ---------------- backends ----------------
def run_local(a) -> dict:
    done = {"n": 0}
    mon = Monitor(
        lambda: max(0, min(a.max_workers, a.burst - done["n"])), a.kcap, interval=0.2
    )
    ex = ProcessPoolExecutor(max_workers=a.max_workers)
    t0 = time.time()
    mon.start()
    futs = [ex.submit(gpu_task, a.hold_sec, 256) for _ in range(a.burst)]
    first = None
    for _ in as_completed(futs):
        if first is None:
            first = time.time() - t0
        done["n"] += 1
    comp = time.time() - t0
    mon.stop()
    ex.shutdown()
    return _record(a.out, "local", a.burst, comp, first, mon)


def run_parsl(a) -> dict:
    import parsl  # lazy
    from parsl.app.app import python_app

    # BIND POINT: load a Parsl config whose executor uses a KubernetesProvider in
    # the experiment namespace (so workers are pods the monitor can see). A
    # demand-scaling provider (max_blocks high) is the realistic "no-politeness"
    # baseline; document the config in the paper.
    parsl.load(parsl.Config())  # replace with the cluster KubernetesProvider config

    app = python_app(gpu_task)
    mon = Monitor(
        kubectl_pod_counter(a.namespace, a.label),
        a.kcap,
        interval=a.interval,
        util_fn=util_from_cmd(a.util_cmd),
    )
    t0 = time.time()
    mon.start()
    futs = [app(a.hold_sec) for _ in range(a.burst)]
    first = None
    for f in futs:
        f.result()
        if first is None:
            first = time.time() - t0
    comp = time.time() - t0
    mon.stop()
    parsl.dfk().cleanup()
    return _record(a.out, "parsl", a.burst, comp, first, mon)


def run_globus(a) -> dict:
    from globus_compute_sdk import Executor  # lazy (formerly funcx)

    # BIND POINT: endpoint_id of a Globus Compute endpoint whose provider launches
    # pods in the namespace. Register the same gpu_task; submit B; poll.
    mon = Monitor(
        kubectl_pod_counter(a.namespace, a.label),
        a.kcap,
        interval=a.interval,
        util_fn=util_from_cmd(a.util_cmd),
    )
    t0 = time.time()
    mon.start()
    with Executor(endpoint_id=a.endpoint) as gce:
        futs = [gce.submit(gpu_task, a.hold_sec) for _ in range(a.burst)]
        first = None
        for f in futs:
            f.result()
            if first is None:
                first = time.time() - t0
    comp = time.time() - t0
    mon.stop()
    return _record(a.out, "globus", a.burst, comp, first, mon)


_BACKENDS = {"local": run_local, "parsl": run_parsl, "globus": run_globus}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--backend", choices=list(_BACKENDS), default="local")
    ap.add_argument("--burst", type=int, default=8)
    ap.add_argument("--kcap", type=int, default=4, help="policy pod cap K")
    ap.add_argument("--hold-sec", type=float, default=8.0, dest="hold_sec")
    ap.add_argument(
        "--max-workers",
        type=int,
        default=8,
        dest="max_workers",
        help="local backend pool size (set > kcap to show over-provisioning)",
    )
    ap.add_argument("--namespace", default="ssu-atlas-ai")
    ap.add_argument(
        "--label", default=None, help="pod selector for parsl/globus workers"
    )
    ap.add_argument("--interval", type=float, default=1.0, help="monitor sample period")
    ap.add_argument(
        "--util-cmd",
        default=None,
        dest="util_cmd",
        help="shell cmd printing mean GPU util 0..1 (DCGM/Prometheus); "
        "omit -> only cap-violation side of rho is reported",
    )
    ap.add_argument("--endpoint", default=None, help="globus compute endpoint_id")
    ap.add_argument("--out", default="out/baseline.json")
    a = ap.parse_args()
    rec = _BACKENDS[a.backend](a)
    m = rec["metrics"]
    print(
        f"[{a.backend}] B={a.burst} completion={rec['burst_completion_s']:.2f}s "
        f"peak={m['peak_concurrency']} (cap {m['cap']}) "
        f"cap_violation={m['cap_violation_fraction']:.2f} -> {a.out}"
    )


if __name__ == "__main__":
    main()
