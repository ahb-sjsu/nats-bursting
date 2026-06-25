# Bursting AI Workloads to a Shared Cluster over NATS: A Compression- and GPU-Aware Pipeline for Effective, Policy-Safe Use of NRP Nautilus

*Draft (practice & experience paper). **Target: CANOPIE-HPC @ SC26** (IEEE format; paper
deadline Aug 14, 2026). The submission artifact is `paper.tex` (IEEEtran) + `paper.bib` +
`figures/`; this markdown carries the same argument in readable form. Alt venues: ECHO @ SC26
(Aug 15), INDIS (Jul 25).*

## Abstract

A researcher with a single workstation and access to a shared GPU cluster (the National
Research Platform's Nautilus) faces real friction turning that access into elastic capacity:
`kubectl`, YAML, cold starts, and no feedback loop into the code they are already running. We
present **nats-bursting**, which lets a workstation treat the cluster as extra GPUs *without
leaving the NATS event loop* — cluster pods join the same message bus as first-class
subscribers, in two shapes (ephemeral Jobs and persistent pools). We compose it with two
sibling tools, **turboquant-pro** (payload compression on the wire) and **batch-probe**
(per-pod GPU right-sizing and thermal governance), into a pipeline for using the shared
cluster *effectively* and *within policy*. We quantify each layer on real infrastructure:
compression yields 8–16× smaller payloads at high fidelity, and on a real bandwidth-limited
link the round-trip win scales with payload from 1.2× (4 KB) to **8.4× (256 KB)**; an
ephemeral burst cold-starts in single-digit seconds; and the whole harness is policy-safe by
construction. We report what is measured and what is not, and release the harness and data.

## 1. Introduction

Shared GPU clusters such as NRP Nautilus exist precisely so that researchers without their
own datacenter can burst. Yet "use the cluster from my workstation" remains awkward: you write
Kubernetes manifests, submit jobs, poll for completion, and shuttle data in and out — none of
it inside the Python event loop where the actual research runs. The friction is high enough
that elastic capacity often goes unused.

This paper describes a small, composable pipeline that closes that gap, and measures it
honestly on the real cluster. Our contributions:

1. A **NATS-native bursting model**: cluster pods are first-class subscribers on the same bus
   as the workstation, in two shapes — ephemeral Jobs (run-to-completion) and persistent pools.
2. A **three-tool composition** for *effective* and *policy-safe* use: nats-bursting moves the
   work, turboquant-pro compresses the payloads, batch-probe right-sizes each pod to its GPU.
3. An **empirical study** on real infrastructure (a workstation, Atlas, and NRP Nautilus),
   reported with its threats to validity stated up front.

This is a practice/experience paper: a working, open system plus measurements, not a new
scheduler. Its value is the integration and the honest characterization of when each layer
helps.

## 2. Background

**NRP Nautilus** is a shared, opportunistic Kubernetes cluster. Its usage policy is the
constraint that shapes the design: small/idle pods are tolerated (CPU≤1, mem≤2 GiB are an
"ignored" range), but groups of pods must sustain utilization (5+ pods must each stay under
40% GPU), Jobs must run to completion and exit cleanly (no `sleep`-camping), and requests
should match usage. "Effective and policy-safe" is therefore not a slogan but a design target.

**NATS / JetStream** provides subject-based publish/subscribe, request–reply, queue groups,
and leaf-node bridging. A leaf node lets pods inside the cluster join a workstation's bus as
if local.

**Cloud bursting** is the general idea of spilling work from a local resource to a remote one.
We use a message bus rather than a job queue or RPC because it makes the cluster a *peer* on
the same fabric the application already uses, rather than an external system to orchestrate.

## 3. System architecture

**nats-bursting** bridges a workstation's NATS server and cluster pods via a leaf node: pods
dial into the bus and subscribe, so submitting work is publishing a message. A controller
manages the two pod shapes — an ephemeral `Job` per burst (run-to-completion, auto-cleaned)
or a persistent pool (long-lived subscribers draining a queue group). A `%%burst` notebook
magic exposes this in the researcher's loop.

**The composition (the paper's thesis).** Two sibling tools make bursting *effective* and
*cheap on the wire*:

- *turboquant-pro* compresses the payloads that ride the bus — embeddings, KV-cache pages,
  feature tensors — with its NATS codec.
- *batch-probe* right-sizes each pod's batch to its GPU (the largest that fits, with headroom,
  via OOM-safe search) so a burst actually saturates the device, and thermally governs the
  *local* orchestration side.

The three are orthogonal and compose: nats-bursting moves the work, turboquant-pro shrinks it,
batch-probe maximizes per-pod utilization.

## 4. Evaluation

We evaluate in three tiers by the infrastructure each needs, mirroring the released
`benchmarks/` harness.

### 4.1 Compression (Tier 1)

On dim-1024 vectors, the NATS codec gives ratios of **7.9× / 10.4× / 15.5×** at 4 / 3 / 2-bit,
with reconstruction cosine **0.995 / 0.978 / 0.94**. Analytic transfer of a 1 MB batch is 84→8
ms at 100 Mbps (net −63 ms including encode) and roughly a wash at 1 Gbps. The finding:
compression is a *knob* that wins when the link is the bottleneck, not on a fast LAN.

**Real-data check.** Random Gaussian vectors are the default; to test whether that is
representative we reran on **real bge-small-en-v1.5 embeddings** (20newsgroups, n=3000). The
ratio and cosine are **identical within 0.001** at every bit-width — the codec's fidelity is
*distribution-agnostic*, consistent with TurboQuant's random-rotation guarantee. The synthetic
benchmark is therefore representative: neither optimistic nor pessimistic.

### 4.2 Transport (Tier 2)

On a loopback NATS bus (no network bottleneck), the ~10× smaller compressed payload still
gives ~6× lower round-trip and throughput for large batches (256-batch: 6.99→1.20 ms p50,
137→783 msgs/s) — payload size dominates round-trip cost even with no link.

The result loopback cannot show is the **real network hop**. Measuring a remote workstation
against a responder on Atlas, co-existing on the production bus over a ~90 ms / ~2 Mbps
tailscale path (a realistic cross-site/WAN burst link), the compression win **scales with
payload**:

| batch | raw (p50) | compressed (p50) | speedup |
|------:|----------:|-----------------:|--------:|
| 1  | 4 KB → 85 ms     | 0.4 KB → 71 ms | 1.2× |
| 16 | 64 KB → 383 ms   | 6 KB → 105 ms  | 3.6× |
| 64 | 256 KB → 1119 ms | 24 KB → 134 ms | **8.4×** |

Tiny payloads stay latency-bound (1.2×); as payload grows on the bandwidth-limited link the
win climbs toward the raw compression ratio (8.4× at 256 KB). This *demonstrates* the Tier-1
crossover on a real link, not merely in the analytic model.

### 4.3 Cluster: cold-start, warm-pool, and scaling (Tier 3)

**Cold-start.** Submitting ephemeral CPU Jobs to NRP (cpu=1/mem=2 GiB ignored range, one pod
at a time, auto-cleaned), submit→complete is **median ~6.6 s (5.1–7.6 s, n=5)**, of which the
pod schedule→container-start (K8s-reported) is ~1–3 s; the rest is API and `kubectl wait`
detection. This is the warm-node, cached-image case.

**Warm-pool and scaling.** A persistent pool of N queue-group worker pods on NRP, driven from
the Atlas hub over the leaf bridge (1 KB tasks, 400/run, driver concurrency 64):

| workers | throughput | p50 | p99 |
|--------:|-----------:|----:|----:|
| 1 | 782/s | 71 ms | 113 ms |
| 2 | 924/s | 68 ms | 80 ms |
| 4 | 936/s | 67 ms | 78 ms |

Two findings. (1) Warm-pool per-task latency is **~67 ms vs ~6.6 s cold-start** — a persistent
pool removes the ~100× cold-start penalty (this is also the burst-path-vs-cold-Job overhead
contrast). (2) Throughput **plateaus ~930/s by two workers**, and honestly so: for trivial
I/O-bound tasks the ceiling is *concurrency ÷ RTT* (Little's law, 64 / 0.067 s ≈ 955/s), not
worker count — one to two workers already saturate the ~67 ms WAN link. Worker-count scaling is
expected to matter for *compute-bound* tasks, where each task occupies a worker.

**Effective use (batch-probe).** The third tool, demonstrated: batch-probe sized a BERT-base-scale
encoder to batch 204 on a GV100 and the burst ran at **94.4% mean / 100% peak GPU utilization** at
a safe 61 °C — far above NRP's >40% sustained-util expectation. (The batch number is bounded by a
safety-capped search range, not device memory; the achieved *utilization* is the result.)

**Not yet measured:** a true cold image pull, a GPU-image cold-start, and a compute-bound scaling
workload (to show worker-count scaling). These are scoped, policy-gated next runs.

## 5. Threats to validity

We state these so the numbers are read correctly; most are now addressed empirically.

- **Synthetic data (Tier 1)** — *addressed*: real bge-small embeddings reproduce the random
  numbers within 0.001 (§4.1). Cosine remains a fidelity proxy, not a downstream-task guarantee.
- **Analytic transfer (Tier 1)** — *addressed*: Tier 2 measures the real round-trip; the
  predicted crossover is observed on a real link.
- **Loopback (Tier 2)** — *addressed*: a real ~2 Mbps hop shows the win scaling 1.2×→8.4×.
  One tailscale (likely relayed) path so far; a characterized datacenter link would pin
  absolute bandwidth. Encode cost is excluded from the transport loop (it is in Tier 1) — the
  speedups are not free.
- **Cold-start realism (Tier 3)** — warm node + cached image + `kubectl wait` detection inflate
  the total; the K8s schedule→run breakdown isolates the cluster-side cost. Cold-pull, GPU-image,
  and NATS-join runs remain.
- **Small n / single cluster** — we report median and range, point-in-time; more reps and
  replication remain. Scoped as a practice study, not a universal claim.
- **Cluster citizenship** — the harness is policy-safe by construction: ignored-range pods,
  ≤1 concurrent pod in the measured runs, exit-0 Jobs, `ttlSecondsAfterFinished` + delete, and a
  `--i-have-checked-nrp-policy` gate. The methodology itself cannot be accused of hoarding a
  shared resource.

## 6. Discussion

The deployment rule is simple and now evidenced: **compress when the link or bus is the
bottleneck.** On a fast LAN it is a wash; on a real WAN-class link the benefit is large and
grows with payload. "Effective" use is batch-probe sizing pods to high per-pod utilization
(meeting NRP's expectation); "policy-safe" is the gate, short runs, and cleanup. Limitations:
a single-cluster study, transport over one real path, and thermal/utilization figures that are
workstation- and cluster-specific. This is an integration and a measurement, not a scheduler.

## 7. Related work

Cloud bursting and function/task systems — HTCondor flocking, Globus Compute (funcX), Ray,
Dask-Jobqueue, Parsl, Covalent — orchestrate remote execution but treat the remote resource as
an external system. Message-bus compute (NATS workers, Celery/RabbitMQ task queues) is the
closest fabric; our distinction is making cluster pods *first-class subscribers* on the
researcher's own bus. Payload compression for ML transport (gradient/activation compression,
embedding/KV-cache quantization) is a deep literature; we contribute a measured account of
*when* it pays on a real burst link. GPU right-sizing and OOM-safe batch search, and
thermal-aware scheduling, are the batch-probe lineage.

## 8. Conclusion & availability

nats-bursting plus turboquant-pro and batch-probe form a small, composable, open pipeline that
makes a shared cluster usable from inside the event loop, effectively and within policy. We
report real numbers for compression (incl. a real-embedding check), transport (loopback and a
real network hop), and cold-start, with threats to validity stated and the persistent-pool
measurements scoped as next work. All three tools are on PyPI; the benchmark harness and the
results files (`results_compression*.json`, `results_transport_realhop.json`) are in-repo and
reproducible.
