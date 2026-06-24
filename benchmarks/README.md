# nats-bursting benchmarks

Quantifies the burst path and its composition with two sibling tools. Three tiers, by
what infrastructure they need.

| Tier | Script | Needs | What it measures |
|---|---|---|---|
| 1 | `bench_compression.py` | CPU only | turboquant-pro payload compression on the wire |
| 2 | `bench_transport.py` | a NATS server | request/reply round-trip latency + throughput (± compression) |
| 3 | `bench_cluster.py` | NRP cluster | cold-start, warm-pool, scaling, kubectl overhead |

## The three-project composition

A burst pipeline made of three shipped tools, each doing one job:

- **nats-bursting** moves AI tasks to a remote cluster over a NATS bus (pods are
  first-class subscribers; ephemeral Jobs or persistent pools).
- **turboquant-pro** compresses the *payloads* (embeddings, KV pages, tensors) so the
  bus carries fewer bytes.
- **batch-probe** sizes each pod's workload to its GPU (largest batch that fits, no OOM)
  and keeps the local driver thermal-safe — so bursts use NRP *effectively* and *within
  policy*.

## Tier 1 — compression (runs now, no cluster)

```bash
pip install turboquant-pro numpy
python benchmarks/bench_compression.py
```

Result (random fp32, this machine): compression **7.9× (4-bit) / 10.4× (3-bit) /
15.5× (2-bit)** at dim 1024, reconstruction cosine **0.995 / 0.978 / 0.94**. Transfer of
a 256×1024 fp32 batch (1 MB):

| link | raw | compressed (3-bit) | net incl. encode |
|---|---:|---:|---:|
| 100 Mbps | 83.9 ms | 8.0 ms | **−63 ms** (big win) |
| 1 Gbps | 8.4 ms | 0.8 ms | +4.8 ms (encode > transfer saved) |

**Takeaway (honest):** compression pays off when the *link* is the bottleneck —
cross-site / WAN bursts to a shared cluster — and is a wash or slight loss on a fast
local LAN. Pick `--compress` accordingly; the codec is a knob, not a default.

## Tier 2 — NATS transport (needs a server)

```bash
docker run -p 4222:4222 nats:latest          # or point NATS_URL at a deployed bus
python benchmarks/bench_transport.py             # raw
python benchmarks/bench_transport.py --compress  # with turboquant-pro codec
```

Reports p50/p99 round-trip and msgs/s per payload size, so you can see the fabric cost
the burst rides on and where compression flips from cost to win on a *real* bus.

## Tier 3 — cluster (NRP; policy-gated)

```bash
# Refuses to run without the ack flag — by design.
python benchmarks/bench_cluster.py --mode cold --i-have-checked-nrp-policy
```

Submits pods to a shared cluster, so it is **gated**: it will not run without
`--i-have-checked-nrp-policy`. NRP has hard rules (sustained >40% GPU util, pod
sizing/limits, ban conditions) — check them, keep runs short, clean up. **Measure, do
not camp.** Per-pod GPU sizing + local thermal governance are delegated to batch-probe.

## Results files
`results_compression.json` (Tier 1) is committed as a reference run; Tiers 2–3 write
their own JSON when run against a server / cluster.
