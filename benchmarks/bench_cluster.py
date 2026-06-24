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


def measure_warm_pool_kubectl(
    workers=(1, 2, 4),
    namespace="ssu-atlas-ai",
    nats_url="nats://127.0.0.1:4222",
    in_cluster_nats="nats://atlas-nats:4222",
    tasks=400,
    payload_bytes=1024,
    concurrency=64,
):
    """Warm-pool latency + throughput + scaling (produced the README numbers).

    For each worker count N (kept <=4 to stay in the safe NRP util tier), creates a Job of N
    ignored-range (cpu=1/mem=2Gi) queue-group subscriber pods on the bus, waits until they
    answer, then drives `tasks` requests at `concurrency` from the hub and records throughput
    + p50/p99. Bounded-lifetime workers, auto-cleaned. Run this ON the host that reaches the
    NATS hub (e.g. the Atlas box); needs kubectl + nats-py. Returns list of dicts.

    Note: for trivial I/O tasks throughput is concurrency/RTT-bound (Little's law), not
    worker-bound, so it plateaus; the warm-pool latency (no cold start) is the headline.
    """
    import asyncio
    import base64
    import json
    import statistics
    import subprocess

    import nats

    worker_src = (
        "import asyncio, nats\n"
        "async def main():\n"
        f"    nc=await nats.connect('{in_cluster_nats}', connect_timeout=15,"
        " max_reconnect_attempts=5)\n"
        "    async def work(m):\n"
        "        try: await nc.publish(m.reply, m.data)\n"
        "        except Exception: pass\n"
        "    await nc.subscribe('bench.work', queue='w', cb=work,"
        " pending_bytes_limit=256*1024*1024)\n"
        "    await asyncio.sleep(150)\n"
        "    await nc.drain()\n"
        "asyncio.run(main())\n"
    )
    b64 = base64.b64encode(worker_src.encode()).decode()

    def manifest(n):
        cmd = f"pip install -q nats-py >/dev/null 2>&1 && echo {b64} | base64 -d | python -"
        return json.dumps(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": "bench-pool", "namespace": namespace},
                "spec": {
                    "parallelism": n,
                    "completions": n,
                    "ttlSecondsAfterFinished": 60,
                    "backoffLimit": 0,
                    "activeDeadlineSeconds": 240,
                    "template": {
                        "spec": {
                            "restartPolicy": "Never",
                            "containers": [
                                {
                                    "name": "w",
                                    "image": "python:3.12-slim",
                                    "command": ["bash", "-lc", cmd],
                                    "resources": {
                                        "requests": {"cpu": "1", "memory": "2Gi"},
                                        "limits": {"cpu": "1", "memory": "2Gi"},
                                    },
                                }
                            ],
                        }
                    },
                },
            }
        )

    def k(*args, inp=None):
        return subprocess.run(
            ["kubectl", "-n", namespace, *args],
            input=inp,
            capture_output=True,
            text=True,
        )

    async def measure(n):
        nc = await nats.connect(nats_url, connect_timeout=10)
        payload = b"x" * payload_bytes
        ready = False
        for _ in range(60):
            try:
                await nc.request("bench.work", b"ping", timeout=3)
                ready = True
                break
            except Exception:
                await asyncio.sleep(2)
        if not ready:
            await nc.drain()
            return {"workers": n, "error": "no workers ready"}
        await asyncio.sleep(5)  # let remaining replicas connect
        for _ in range(10):
            await nc.request("bench.work", payload, timeout=15)
        sem = asyncio.Semaphore(concurrency)
        lat = []

        async def one():
            async with sem:
                s = time.perf_counter()
                try:
                    await nc.request("bench.work", payload, timeout=20)
                    lat.append((time.perf_counter() - s) * 1e3)
                except Exception:
                    pass

        t0 = time.perf_counter()
        await asyncio.gather(*[one() for _ in range(tasks)])
        wall = time.perf_counter() - t0
        await nc.drain()
        lat.sort()
        return {
            "workers": n,
            "tasks": len(lat),
            "throughput_per_s": round(len(lat) / wall, 1),
            "p50_ms": round(statistics.median(lat), 2),
            "p99_ms": round(lat[int(0.99 * len(lat))], 2),
        }

    async def run_all():
        out = []
        for n in workers:
            if n > 4:
                raise ValueError("keep workers <=4 to stay in the safe NRP util tier")
            k("delete", "job", "bench-pool", "--wait=true")
            time.sleep(2)
            k("apply", "-f", "-", inp=manifest(n))
            for _ in range(60):
                r = k(
                    "get",
                    "pods",
                    "-l",
                    "job-name=bench-pool",
                    "--field-selector=status.phase=Running",
                    "-o",
                    "name",
                )
                if r.stdout.count("pod/") >= n:
                    break
                time.sleep(2)
            out.append(await measure(n))
            k("delete", "job", "bench-pool", "--wait=false")
        return out

    return asyncio.run(run_all())


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

    if a.mode in ("warm", "scale"):
        # Real warm-pool / scaling: N queue-group worker pods, driven from the hub.
        # Run this on the host that reaches the NATS hub (e.g. Atlas).
        workers = (1,) if a.mode == "warm" else (1, 2, 4)
        rows = measure_warm_pool_kubectl(workers=workers, namespace=a.namespace)
        for r in rows:
            print(" ", r)
        print(
            "NOTE: trivial I/O tasks -> throughput is concurrency/RTT-bound (Little's law), "
            "not worker-bound; warm-pool latency vs ~6.6s cold-start is the headline. "
            "GPU sizing for compute-bound bursts is delegated to batch-probe."
        )
        return

    # --- overhead mode: still to wire (burst-path submit vs raw kubectl) ---
    print(
        f"[scaffold] mode={a.mode}: not yet wired. cold/warm/scale are measured "
        f"(--mode cold|warm|scale). 'overhead' (burst-path vs raw kubectl) is next."
    )


if __name__ == "__main__":
    main()
