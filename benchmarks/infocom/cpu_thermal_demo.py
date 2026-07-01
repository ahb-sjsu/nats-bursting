"""H4 micro-tier demo: batch-probe ThermalController holding a CPU thermal
setpoint under a compute burst (its native actuator = worker/thread count).

Faithful use of batch-probe's ThermalMgr: the controller reads CPU temperature
(lm-sensors) through a Kalman filter and sets a recommended worker count; the pool
tracks it, so temperature is held near the setpoint by throttling parallelism
*before* overshoot (predictive PID + feedforward).

SAFETY (Atlas thermals are a known hazard -- ~99 C at 40 unthrottled workers):
  * conservative cap (max_threads small), self-limiting by construction;
  * hard kill-switch: if temp exceeds --abort-temp, kill all workers and stop;
  * the unthrottled baseline is NOT run (it is the unsafe case); we cite it.

Writes a time series (t, temp, target_threads, active) to --out.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

WORKER = (
    "import numpy as np\n"
    "a=np.random.rand(768,768); x=a\n"
    "while True: x=(x@a)%7.0+1.0\n"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setpoint", type=float, default=82.0)
    ap.add_argument("--max-threads", type=int, default=12, dest="max_threads")
    ap.add_argument("--min-threads", type=int, default=1, dest="min_threads")
    ap.add_argument("--abort-temp", type=float, default=90.0, dest="abort_temp")
    ap.add_argument("--duration", type=float, default=90.0)
    ap.add_argument("--pybin", default=sys.executable)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import batch_probe._thermal as bt
    from batch_probe import ThermalController

    ctl = ThermalController(
        target_temp=a.setpoint, max_threads=a.max_threads, min_threads=a.min_threads,
        poll_interval=1.5, verbose=False,
    )
    ctl.start()

    workers: list[subprocess.Popen] = []
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")

    def spawn():
        workers.append(subprocess.Popen([a.pybin, "-c", WORKER], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def kill_to(n):
        while len(workers) > n:
            p = workers.pop()
            try:
                p.terminate()
            except Exception:
                pass

    samples = []
    t0 = time.time()
    aborted = False
    try:
        while time.time() - t0 < a.duration:
            temp = bt._read_cpu_temp()
            if temp is not None and temp >= a.abort_temp:  # hard safety
                kill_to(0)
                aborted = True
                samples.append({"t": round(time.time() - t0, 1), "temp": temp,
                                "target": 0, "active": 0, "abort": True})
                break
            target = ctl.get_threads()
            if len(workers) < target:
                spawn()
            elif len(workers) > target:
                kill_to(target)
            # reap any dead
            workers[:] = [p for p in workers if p.poll() is None]
            samples.append({"t": round(time.time() - t0, 1),
                            "temp": temp, "target": target, "active": len(workers)})
            time.sleep(1.0)
    finally:
        kill_to(0)
        ctl.stop()

    temps = [s["temp"] for s in samples if s.get("temp") is not None]
    res = {
        "experiment": "H4_cpu_thermal", "setpoint": a.setpoint,
        "max_threads": a.max_threads, "abort_temp": a.abort_temp, "aborted": aborted,
        "peak_temp": max(temps) if temps else None,
        "mean_temp_after_warmup": (
            round(sum(t for t in temps[10:]) / len(temps[10:]), 1) if len(temps) > 10 else None),
        "mean_active_after_warmup": (
            round(sum(s["active"] for s in samples[10:]) / len(samples[10:]), 1)
            if len(samples) > 10 else None),
        "n_samples": len(samples),
    }
    json.dump({"result": res, "samples": samples}, open(a.out, "w"), indent=2)
    print(f"[cpu-thermal] setpoint={a.setpoint} peak={res['peak_temp']} "
          f"mean_after={res['mean_temp_after_warmup']} "
          f"mean_active={res['mean_active_after_warmup']} aborted={aborted}", flush=True)


if __name__ == "__main__":
    main()
