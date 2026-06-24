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


def bench_cold_start(client, descriptor, reps):
    """Ephemeral Job-shape round trip, pod boot included."""
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
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--gpu", type=int, default=1)
    ap.add_argument("--i-have-checked-nrp-policy", action="store_true")
    a = ap.parse_args()
    _require_policy_ack(a)

    # --- batch-probe: size the per-pod workload to the GPU before bursting ---
    # from batch_probe import probe_batch_size, ThermalController
    # max_bs = probe_batch_size(model, sample_input, device="cuda", headroom=0.1)
    # thermal = ThermalController(max_temp_c=82)   # govern the local driver side
    #
    # --- nats-bursting: submit ---
    # from nats_bursting import Client, JobDescriptor, TaskDispatcher
    # desc = JobDescriptor(image=..., gpu=a.gpu, command=[...])  # confirm fields per descriptor.py
    # with Client(servers="nats://<nrp-bus>") as client:
    #     if a.mode == "cold":
    #         lat = bench_cold_start(client, desc, a.reps)
    #         ...report p50/p99 cold-start...
    #
    # TODO (run on NRP): wire the four modes against the deployed controller + a warm pool,
    # report cold-start vs warm-pool deltas, scaling curve, and burst-vs-kubectl overhead.
    print(
        f"[scaffold] mode={a.mode} reps={a.reps} gpu={a.gpu} — wire against a deployed "
        f"NRP controller; size pods with batch-probe; keep runs short + clean up."
    )


if __name__ == "__main__":
    main()
