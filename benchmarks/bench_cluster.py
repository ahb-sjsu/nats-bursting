#!/usr/bin/env python3
"""Tier-3 benchmark: the burst path against a real cluster (NRP Nautilus).

Measures what only a live cluster can show:
  - cold-start: ephemeral Job-shape round trip (pod boot included)
  - warm-pool: persistent-pool latency + sustained throughput (no cold start)
  - scaling: throughput vs N pool replicas (JetStream backpressure)
  - overhead: burst-path submit latency vs direct kubectl Job creation

Effective, policy-safe NRP usage is delegated to **batch-probe**:
  - `batch_probe.probe_batch_size(...)` sizes each pod's workload to its GPU (largest
    batch that fits, with safety headroom) so bursts actually saturate the device.
  - `batch_probe.ThermalController` governs the *local* orchestration side so the
    workstation driving the burst never overheats.

Compression (Tier 1) and this tier compose: turboquant-pro shrinks the payloads on the
wire; batch-probe maximizes per-pod GPU work; nats-bursting moves them over NATS.

!!! This tier submits pods to a shared cluster. It refuses to run without
    --i-have-checked-nrp-policy, because NRP has hard usage rules (sustained >40% GPU
    util, pod sizing/limits, ban conditions). CHECK THE POLICY, keep runs short, and
    clean up. Measure, do not camp.

Measured cold-start (NRP `ssu-atlas-ai`, 2026; ephemeral CPU Job at cpu=1/mem=2Gi -- the
policy "ignored" range; warm node, cached `python:3.12-slim`; one pod at a time;
auto-cleaned). Submit -> Completed, submitting-host wall clock, 5 runs:

    5.13, 6.14, 6.57, 7.44, 7.60 s     (median ~6.6 s)

of which the pod schedule -> container-start (K8s-reported, 1 s resolution) is ~1-3 s; the
remainder is API + `kubectl wait` detection. Caveats: cached image (a cold pull on a fresh
node adds pull time; a GPU image adds much more); CPU job (no device init); single cluster;
no NATS-join yet. `measure_cold_start_kubectl()` below is the policy-safe path that produced
these; the full burst-ready metric (incl. NATS join) needs a worker image with the client.
"""

import argparse
import sys
import time


def _require_policy_ack(args):
    if not args.i_have_checked_nrp_policy:
        sys.exit(
            "Refusing to submit cluster pods.\n"
            "Re-run with --i-have-checked-nrp-policy after confirming NRP limits "
            "(util >40%, pod sizing, ban conditions). This guard is intentional."
        )


_JOB_MANIFEST = """apiVersion: batch/v1
kind: Job
metadata: {{name: {name}, namespace: {ns}}}
spec:
  ttlSecondsAfterFinished: 90
  backoffLimit: 0
  activeDeadlineSeconds: 300
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: w
        image: {image}
        command: ["python", "-c", "print('burst ok')"]
        resources:
          requests: {{cpu: "1", memory: 2Gi}}
          limits: {{cpu: "1", memory: 2Gi}}
"""


def measure_cold_start_kubectl(
    reps=5, namespace="ssu-atlas-ai", image="python:3.12-slim"
):
    """Policy-safe ephemeral-Job cold-start measurement (produced the numbers above).

    Submits tiny ignored-range (cpu=1, mem=2Gi) CPU Jobs ONE AT A TIME, times
    submit->complete on the submitting host's wall clock, and reads the pod's own K8s
    timestamps for the schedule->container-start breakdown. Auto-cleans via
    ttlSecondsAfterFinished + delete. Stays within NRP policy (ignored range, <=1 pod,
    exits 0, cleaned up). Needs a kubectl context on the namespace. Returns list of dicts.
    """
    import subprocess

    def k(*a, inp=None):
        return subprocess.run(
            ["kubectl", "-n", namespace, *a], input=inp, capture_output=True, text=True
        )

    def epoch(ts):
        return subprocess.run(
            ["date", "-d", ts, "+%s"], capture_output=True, text=True
        ).stdout.strip()

    rows = []
    for n in range(1, reps + 1):
        name = f"bench-cs-{n}"
        t0 = time.perf_counter()
        k(
            "apply",
            "-f",
            "-",
            inp=_JOB_MANIFEST.format(name=name, ns=namespace, image=image),
        )
        k("wait", "--for=condition=complete", f"job/{name}", "--timeout=300s")
        total = round(time.perf_counter() - t0, 2)
        pod = k(
            "get",
            "pods",
            "-l",
            f"job-name={name}",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ).stdout.strip()
        tc = k(
            "get", "pod", pod, "-o", "jsonpath={.metadata.creationTimestamp}"
        ).stdout.strip()
        tr = k(
            "get",
            "pod",
            pod,
            "-o",
            "jsonpath={.status.containerStatuses[0].state.terminated.startedAt}",
        ).stdout.strip()
        sched = (int(epoch(tr)) - int(epoch(tc))) if tc and tr else None
        rows.append(
            {"run": n, "submit_to_complete_s": total, "schedule_to_run_s": sched}
        )
        k("delete", "job", name, "--wait=false")
    return rows


def bench_cold_start(client, descriptor, reps):
    """Ephemeral Job-shape round trip via the NATS controller (full burst path; needs a
    deployed nats-bursting controller). Complements measure_cold_start_kubectl, which
    measures the raw K8s Job lifecycle without the controller."""
    lat = []
    for _ in range(reps):
        t = time.perf_counter()
        res = client.submit_and_wait(descriptor, timeout=300)
        if res.accepted:
            lat.append(time.perf_counter() - t)
    return lat


async def bench_warm_pool(dispatcher, subject, tasks):
    """Persistent-pool latency + throughput (no cold start)."""
    t = time.perf_counter()
    ids = await dispatcher.submit_many(subject, tasks)
    results = await dispatcher.collect(ids, timeout=300)
    wall = time.perf_counter() - t
    return {
        "n": len(tasks),
        "wall_s": wall,
        "tasks_per_s": len(tasks) / wall,
        "n_results": len(results),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode", choices=["cold", "warm", "scale", "overhead"], default="cold"
    )
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--gpu", type=int, default=1)
    ap.add_argument("--namespace", default="ssu-atlas-ai")
    ap.add_argument("--i-have-checked-nrp-policy", action="store_true")
    a = ap.parse_args()
    _require_policy_ack(a)

    if a.mode == "cold":
        # Real, policy-safe cold-start: tiny ignored-range CPU Jobs, one at a time.
        import statistics

        rows = measure_cold_start_kubectl(reps=a.reps, namespace=a.namespace)
        tot = [r["submit_to_complete_s"] for r in rows]
        sch = [
            r["schedule_to_run_s"] for r in rows if r["schedule_to_run_s"] is not None
        ]
        for r in rows:
            print(
                f"  run {r['run']}: submit->complete {r['submit_to_complete_s']}s "
                f"(schedule->run {r['schedule_to_run_s']}s)"
            )
        print(
            f"submit->complete: median {statistics.median(tot):.2f}s "
            f"[{min(tot):.2f}, {max(tot):.2f}] over n={len(tot)}; "
            f"schedule->run median {statistics.median(sch) if sch else 'NA'}s"
        )
        print(
            "NOTE: warm node + cached image; CPU job (no GPU/NATS-join). See module "
            "docstring + README 'threats to validity'."
        )
        return

    # --- modes still requiring a deployed controller + warm pool (future work) ---
    # GPU bursts: size each pod with batch-probe.probe_batch_size(...) and govern the
    # local driver with batch-probe.ThermalController; submit via nats_bursting.Client /
    # TaskDispatcher (see bench_cold_start / bench_warm_pool above).
    print(
        f"[scaffold] mode={a.mode}: needs a deployed nats-bursting controller + warm pool. "
        f"cold-start is wired and measured (--mode cold). warm/scale/overhead are next."
    )


if __name__ == "__main__":
    main()
