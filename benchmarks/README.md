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

**Measured on Atlas** (dedicated `nats-server` on loopback, 800 iters, dim 1024, 3-bit):

| batch | raw p50 / p99 / msgs·s⁻¹ | compressed p50 / p99 / msgs·s⁻¹ | round-trip speedup |
|---|---|---|---|
| 1   | 0.52 / 1.01 ms / 1768 | 0.38 / 0.90 ms / 2261 | 1.4× |
| 32  | 1.69 / 3.12 ms / 561  | 0.40 / 1.37 ms / 2127 | **4.2×** |
| 256 | 6.99 / 11.34 ms / 137 | 1.20 / 2.61 ms / 783  | **5.8×** |

Even on a loopback bus (no network bottleneck), the ~10× smaller payload gives ~6× lower
round-trip and throughput for large batches — payload size dominates round-trip cost. This
measures transport of an already-encoded payload; per-message encode cost is in Tier 1, so
the deployment rule stays: compress when the link (or the bus) is the bottleneck.

## Tier 3 — cluster (NRP; policy-gated)

```bash
# Refuses to run without the ack flag — by design.
python benchmarks/bench_cluster.py --mode cold --i-have-checked-nrp-policy
```

Submits pods to a shared cluster, so it is **gated**: it will not run without
`--i-have-checked-nrp-policy`. NRP has hard rules (sustained >40% GPU util, pod
sizing/limits, ban conditions) — check them, keep runs short, clean up. **Measure, do
not camp.** Per-pod GPU sizing + local thermal governance are delegated to batch-probe.

**Measured cold-start** (NRP `ssu-atlas-ai`; ephemeral CPU Job, cpu=1/mem=2Gi ignored
range; one pod at a time; auto-cleaned): submit→complete **5.1 / 6.1 / 6.6 / 7.4 / 7.6 s**
(median ~6.6 s, n=5); pod schedule→container-start (K8s-reported) ~1–3 s.

## Methodology & threats to validity (anticipating the critic)

We state these up front so the numbers are read correctly; each has a planned fix.

1. **Synthetic vs. real data (Tier 1).** Ratios/cosine use random Gaussian vectors;
   real embeddings differ. *Mitigation:* turboquant-pro's compression is independently
   validated on real embeddings and model activations elsewhere; rerun Tier 1 on a real
   embedding set to confirm. Cosine is a fidelity proxy, **not** a downstream-task
   guarantee — don't over-read it (the same "cosine ≠ task quality" caveat as tq-pro).
2. **Analytic vs. measured transfer (Tier 1).** The transfer-time table is analytic
   (bytes ÷ bandwidth). *Mitigation:* Tier 2 measures the real NATS round-trip; the WAN
   crossover claim is the analytic encode-vs-transfer model, to be confirmed on a real link.
3. **Loopback transport (Tier 2).** Measured on loopback (no network bottleneck), which
   *understates* compression's benefit — so it is a conservative lower bound, not an
   inflated one. Encode cost is **excluded** from the Tier-2 loop (payload pre-encoded)
   and reported in Tier 1; don't read Tier-2 speedups as free. *Planned:* a
   workstation→NRP hop to show the real-link crossover.
4. **Cold-start realism (Tier 3).** Warm node + cached image, so ~6.6 s reflects
   schedule+create+API detection, **not** a cold image pull; the K8s schedule→run
   breakdown (1–3 s) isolates the cluster-side cost, and `kubectl wait` detection inflates
   the *total* (which is why we report the breakdown too). CPU job, no GPU init, no
   NATS-join. *Planned:* fresh-node/cold-pull, a GPU-image run, and the full burst-ready
   (NATS-join) metric via a worker image.
5. **Statistical rigor.** Small n (5); we report median **and** range, not a single point.
   Cluster load and network vary, so these are point-in-time. *Planned:* more reps across
   sessions; Tier-1 uses a fixed seed.
6. **Baselines.** Tier 2 carries an internal raw-vs-compressed baseline; Tier 3's
   burst-path-vs-raw-`kubectl` *overhead* comparison is the next mode to wire.
7. **Generality.** One cluster, one namespace, specific hardware — scoped as a
   practice/experience study, not a universal claim. Scripts are released for replication.
8. **Cluster-citizenship (a reviewer of a different kind).** The harness is policy-safe by
   construction: ignored-range pods, ≤1 concurrent, exit-0 Jobs, `ttlSecondsAfterFinished`
   + delete, and the `--i-have-checked-nrp-policy` gate — so the methodology itself can't
   be accused of hoarding or abusing a shared resource.

## Results files
`results_compression.json` (Tier 1) is committed as a reference run; Tiers 2–3 write
their own JSON when run against a server / cluster.
