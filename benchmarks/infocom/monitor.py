"""Shared policy monitor for E8 + baselines.

Samples concurrency (and optional GPU util / extra phase counts, e.g. pending
pods) every `interval` s, so run.py E8 policies and baselines.py frameworks emit
the *same* metrics and land on one goodput-rho Pareto.

Over-admission rho (the Prop. 2 quantity) is operationalised as the fraction of
epochs in which the guest held a non-productive pod -- a pod **Pending** (asked for
a slot it could not get) or **running below the util floor** (needs a GPU-util
source via util_fn). cap_violation_fraction (concurrency > K) is always available.
"""

from __future__ import annotations

import subprocess
import threading
import time

UTIL_FLOOR = 0.40  # GPU utilization floor U (policy)


class Monitor(threading.Thread):
    """count_fn -> running concurrency; util_fn -> 0..1 GPU util (optional);
    extra_fns -> named per-sample counts (e.g. {"pending": fn})."""

    def __init__(
        self,
        count_fn,
        kcap: int,
        interval: float = 1.0,
        util_fn=None,
        extra_fns: dict | None = None,
    ):
        super().__init__(daemon=True)
        self.count_fn, self.kcap, self.interval, self.util_fn = (
            count_fn,
            kcap,
            interval,
            util_fn,
        )
        self.extra_fns = extra_fns or {}
        self._ev = threading.Event()  # not _stop: Thread._stop is an internal method
        self.samples: list[dict] = []
        self.t0 = time.time()

    def run(self) -> None:
        while not self._ev.is_set():
            s = {
                "t": round(time.time() - self.t0, 3),
                "n": self.count_fn(),
                "util": self.util_fn() if self.util_fn else None,
            }
            for k, fn in self.extra_fns.items():
                s[k] = fn()
            self.samples.append(s)
            self._ev.wait(self.interval)

    def stop(self) -> None:
        self._ev.set()
        self.join(timeout=3)

    def metrics(self) -> dict:
        ns = [s["n"] for s in self.samples] or [0]
        utils = [s["util"] for s in self.samples if s.get("util") is not None]
        out = {
            "peak_concurrency": max(ns),
            "cap": self.kcap,
            "cap_violation_fraction": sum(1 for n in ns if n > self.kcap) / len(ns),
            "util_floor_breach_fraction": (
                sum(1 for u in utils if u < UTIL_FLOOR) / len(utils) if utils else None
            ),
            "n_samples": len(ns),
        }
        if self.samples and any("pending" in s for s in self.samples):
            out["over_admission_fraction"] = sum(
                1
                for s in self.samples
                if (s.get("pending") or 0) > 0
                or (s.get("util") is not None and s["util"] < UTIL_FLOOR)
            ) / len(self.samples)
        return out


def kubectl_pod_counter(ns: str, label: str | None = None, phase: str = "Running"):
    sel = ["-l", label] if label else []
    fsel = [f"--field-selector=status.phase={phase}"] if phase else []

    def _c() -> int:
        r = subprocess.run(
            ["kubectl", "-n", ns, "get", "pods", *sel, *fsel, "-o", "name"],
            capture_output=True,
            text=True,
        )
        return len([x for x in r.stdout.splitlines() if x.strip()])

    return _c


def util_from_cmd(cmd: str | None):
    """Pluggable GPU-util source (e.g. a DCGM/Prometheus query) printing 0..1."""
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
