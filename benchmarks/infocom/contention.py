"""Contention generator for the E8 protocol (see E8_PROTOCOL.md).

Drives a controlled, time-varying competitor occupancy c(t) over a bounded GPU
slice of size C, so the guest's available capacity a(t) = C - c(t) is known ground
truth. Each epoch it reconciles the number of running competitor workloads to the
profile target, with real-compute (no-sleep) self-expiring workloads, and logs the
realized occupancy so a(t) can be reconstructed.

Backends:
  local : competitors are local subprocesses running a bounded matmul (dry-run / a
          single owned node) -- runnable here for a smoke test.
  k8s   : competitors are Kubernetes Jobs (real cluster) -- bound to kubectl; the
          calls are marked and require a live namespace.

    python contention.py --profile square --C 4 --c-hi 3 --tau 10 --epochs 60 \
                         --backend local --out out/contention_square.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from abc import ABC, abstractmethod

# --- real-compute competitor (no sleep): bounded numpy matmul, then exit 0 ---
_BURN = (
    "import time,numpy as np;"
    "t=time.time()+{sec};a=np.random.rand(1024,1024);"
    "x=a\n"
    "while time.time()<t: x=(x@a)%7.0+1.0\n"
    "print('done')"
)


def profile_target(name: str, t: int, a: argparse.Namespace) -> int:
    """Return the target competitor count c(t) at epoch t for the chosen profile."""
    if name == "square":
        return a.c_hi if (t // a.tau) % 2 == 0 else a.c_lo
    if name == "ramp":
        frac = min(1.0, t / max(1, a.epochs - 1))
        return int(round(a.c_lo + frac * (a.c_hi - a.c_lo)))
    if name == "poisson":
        # expected occupancy ~ lam*hold, clamped to [0, C-1] (leave a slot for the guest)
        return min(a.C - 1, max(0, int(round(random.gauss(a.lam * a.hold, 0.7)))))
    if name == "markov":
        # Two-state {c_lo, c_hi} DTMC with per-epoch flip prob p_flip. This is the
        # capacity process the INFOCOM theory analyzes: the lag-D autocorrelation is
        # r(D) = (1-2*p_flip)^D and the coherence time is tau_c = -1/ln(1-2*p_flip),
        # so sweeping --p-flip sweeps tau_c and traces the feedback-advantage law
        # Delta(D) = 1/2 * r(D). State persists across epochs in a._mk_state.
        s = getattr(a, "_mk_state", None)
        if s is None:
            s = random.random() < 0.5
        elif random.random() < a.p_flip:
            s = not s
        a._mk_state = s
        return a.c_hi if s else a.c_lo
    raise SystemExit(f"unknown profile {name}")


class Backend(ABC):
    @abstractmethod
    def reconcile(self, target: int) -> int:
        """Bring running competitor count to `target`; return the realized count."""

    @abstractmethod
    def shutdown(self) -> None: ...


class LocalBackend(Backend):
    """Competitors as local subprocesses (dry-run / single owned node)."""

    def __init__(self, hold_sec: float) -> None:
        self.hold = hold_sec
        self.procs: list[subprocess.Popen] = []

    def _prune(self) -> None:
        self.procs = [p for p in self.procs if p.poll() is None]

    def reconcile(self, target: int) -> int:
        self._prune()
        while len(self.procs) < target:
            self.procs.append(
                subprocess.Popen(
                    [sys.executable, "-c", _BURN.format(sec=self.hold)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        while len(self.procs) > target:  # decrease c(t): drop extras
            self.procs.pop().kill()
        self._prune()
        return len(self.procs)

    def shutdown(self) -> None:
        for p in self.procs:
            p.kill()
        self.procs = []


class K8sBackend(Backend):
    """Competitors as Kubernetes Jobs (real cluster). Requires kubectl + namespace.

    Compliance: each Job runs real GPU matmul (image `--image`) for `--hold-sec`
    then exits 0; labelled `infocom-competitor` for reconciliation. The generator
    never exceeds C, and the guest's run.py is launched with --kcap = K - c_max so
    competitor + guest <= K at all times.
    """

    def __init__(self, image: str, hold_sec: float, ns: str, gpu: int = 1) -> None:
        self.image, self.hold, self.ns, self.gpu = image, hold_sec, ns, gpu
        self._jobs: list[str] = []  # competitor Job names we created
        self._seq = 0

    def _kubectl(self, *args: str, inp: str | None = None):
        return subprocess.run(
            ["kubectl", "-n", self.ns, *args],
            input=inp,
            capture_output=True,
            text=True,
        )

    def _job_manifest(self, name: str) -> str:
        """A Job that pins one GPU with real matmul for hold_sec, then exits 0.

        Real compute (no sleep -> ban-safe), exit-0 + ttlSecondsAfterFinished for
        clean-up, GPU request to occupy a slot, cpu=1/memory=2Gi in the ignored range.
        Built line-by-line like nats_bursting.pool.pool_manifest.
        """
        hold = int(self.hold)
        res = {
            "requests": {"cpu": "1", "memory": "2Gi", "nvidia.com/gpu": str(self.gpu)},
            "limits": {"cpu": "1", "memory": "2Gi", "nvidia.com/gpu": str(self.gpu)},
        }
        burn = [
            "python3 -u - <<'PYEOF'",
            "import time, torch",
            f"t = time.time() + {hold}",
            "x = torch.randn(4096, 4096, device='cuda')",
            "while time.time() < t:",
            "    x = (x @ x).remainder_(7.0).add_(1.0)",
            "torch.cuda.synchronize(); print('competitor done')",
            "PYEOF",
        ]
        lines = [
            "apiVersion: batch/v1",
            "kind: Job",
            "metadata:",
            f"  name: {name}",
            f"  namespace: {self.ns}",
            "  labels: {infocom: competitor}",
            "spec:",
            "  backoffLimit: 0",
            f"  activeDeadlineSeconds: {hold + 60}",
            "  ttlSecondsAfterFinished: 30",
            "  template:",
            "    metadata:",
            "      labels: {infocom: competitor}",
            "    spec:",
            "      restartPolicy: Never",
            "      containers:",
            "      - name: comp",
            f"        image: {self.image}",
            f"        resources: {json.dumps(res)}",
            '        command: ["/bin/bash", "-c"]',
            "        args:",
            "        - |",
            *["          " + ln for ln in burn],
        ]
        return "\n".join(lines) + "\n"

    def _prune(self) -> None:
        """Drop Jobs that are no longer active (completed, failed, or gone)."""
        alive = []
        for n in self._jobs:
            r = self._kubectl("get", "job", n, "-o", "jsonpath={.status.active}")
            if r.returncode == 0 and r.stdout.strip() not in ("", "0"):
                alive.append(n)
        self._jobs = alive

    def _count(self) -> int:
        """Realized occupancy = competitor pods actually Running."""
        r = self._kubectl(
            "get",
            "pods",
            "-l",
            "infocom=competitor",
            "--field-selector=status.phase=Running",
            "-o",
            "name",
        )
        return len([x for x in r.stdout.splitlines() if x.strip()])

    def reconcile(self, target: int) -> int:
        self._prune()
        while len(self._jobs) < target:
            self._seq += 1
            name = f"infocom-comp-{self._seq}"
            self._kubectl("apply", "-f", "-", inp=self._job_manifest(name))
            self._jobs.append(name)
        while len(self._jobs) > target:  # decrease c(t): drop newest
            self._kubectl(
                "delete", "job", self._jobs.pop(), "--ignore-not-found", "--wait=false"
            )
        return self._count()

    def shutdown(self) -> None:
        self._kubectl("delete", "job", "-l", "infocom=competitor", "--ignore-not-found")
        self._jobs = []


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--profile", choices=["square", "ramp", "poisson", "markov"], default="square"
    )
    ap.add_argument("--C", type=int, default=4, help="contended slice size (slots)")
    ap.add_argument("--c-lo", type=int, default=1, dest="c_lo")
    ap.add_argument("--c-hi", type=int, default=3, dest="c_hi")
    ap.add_argument("--tau", type=int, default=10, help="square half-period (epochs)")
    ap.add_argument(
        "--p-flip",
        type=float,
        default=0.1,
        dest="p_flip",
        help="markov per-epoch flip prob; tau_c = -1/ln(1-2*p_flip)",
    )
    ap.add_argument("--lam", type=float, default=0.5, help="poisson arrival rate")
    ap.add_argument(
        "--hold", type=float, default=4.0, help="poisson mean hold (epochs)"
    )
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--epoch-sec", type=float, default=1.0, dest="epoch_sec")
    ap.add_argument(
        "--hold-sec",
        type=float,
        default=8.0,
        dest="hold_sec",
        help="competitor compute duration per launch",
    )
    ap.add_argument("--backend", choices=["local", "k8s"], default="local")
    ap.add_argument("--image", default="ghcr.io/ahb-sjsu/nats-bursting-worker:latest")
    ap.add_argument("--namespace", default="ssu-atlas-ai")
    ap.add_argument("--out", default="out/contention.jsonl")
    a = ap.parse_args()
    if max(a.c_lo, a.c_hi) > a.C:
        ap.error(
            "c_hi/c_lo must be <= C (compliance: competitor never exceeds the slice)"
        )

    backend: Backend = (
        LocalBackend(a.hold_sec)
        if a.backend == "local"
        else K8sBackend(a.image, a.hold_sec, a.namespace)
    )
    t0 = time.time()
    with open(a.out, "w", encoding="utf-8") as f:
        for t in range(a.epochs):
            target = min(a.C, max(0, profile_target(a.profile, t, a)))
            realized = backend.reconcile(target)
            rec = {
                "epoch": t,
                "t_s": round(time.time() - t0, 3),
                "C": a.C,
                "c_target": target,
                "c_realized": realized,
                "a_target": a.C - target,
            }
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"epoch {t:3d}  c={realized}/{target}  a={a.C-realized}", flush=True)
            dt = a.epoch_sec - ((time.time() - t0) % a.epoch_sec)
            time.sleep(max(0.0, dt))
    backend.shutdown()
    print(f"[contention] {a.profile} done; ground-truth a(t) in {a.out}")


if __name__ == "__main__":
    main()
