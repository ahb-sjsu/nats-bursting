# Short systems paper — outline

**Working title:** *Bursting AI Workloads to a Shared Cluster over NATS: A Compression- and
GPU-Aware Pipeline for Effective, Policy-Safe Use of NRP Nautilus*

**Target:** CANOPIE-HPC @ SC26 (Containers & New Orchestration Paradigms in HPC) — IEEE format,
paper deadline **Aug 14, 2026**; artifact required (we have it). Alt: ECHO @ SC26 (Aug 15,
edge–cloud–HPC continuum), INDIS @ SC26 (Jul 25, networking/data-movement angle), or PEARC27
(2027). Audience: the SC/NRP research-computing community that lives this pain.

**Status:** Tier 1 (random **+ real-embedding check**), Tier 2 (loopback **+ real network
hop**), and Tier 3 (cold-start **+ warm-pool + scaling**) all have real numbers (committed in
`benchmarks/`); remaining: a true cold image-pull, a GPU-image/GPU-util run, and a compute-bound
scaling load. A threats-to-validity section (§5) anticipates the reviewer objections.

---

## Abstract (draft target)
A researcher with one workstation and access to a shared GPU cluster (NRP Nautilus) faces real
friction turning that access into elastic capacity. We present **nats-bursting**, which lets a
workstation treat the cluster as extra GPUs *without leaving the NATS event loop* — pods join
the same bus as first-class subscribers, in two shapes (ephemeral Jobs, persistent pools). We
compose it with two sibling tools — **turboquant-pro** (payload compression on the wire) and
**batch-probe** (per-pod GPU right-sizing + thermal governance) — into a pipeline that uses the
shared cluster *effectively* and *within policy*. We quantify each layer; e.g., compression
gives 8–16× smaller payloads (cosine ≥0.94–0.995) and ~6× lower NATS round-trip for large
batches, with an honest crossover where the link, not the codec, decides the win.

## 1. Introduction
- The gap: shared clusters (NRP) exist, but "use it from my workstation" is awkward (kubectl,
  YAML, cold starts, no feedback loop). Researchers want elastic GPUs *inside* their normal loop.
- Contribution: (i) a NATS-native bursting model (pods as first-class subscribers; Jobs vs
  pools); (ii) a 3-tool pipeline for *effective* + *policy-safe* use; (iii) an empirical study.
- Honest scope: practice/experience paper — a working, open system + measurements, not a new
  scheduler.

## 2. Background
- NRP Nautilus: shared, opportunistic K8s; usage policy (sustained util, pod limits) → why
  "effective + policy-safe" matters.
- NATS / JetStream: subjects, request-reply, queue groups, leaf nodes.
- Cloud bursting: the concept; why a message bus (vs job queue / RPC).

## 3. System architecture
- **nats-bursting**: leaf-node bridge topology; the controller (Go); the `%%burst` magic;
  ephemeral `Job` vs persistent `Deployment` pool; "pods are first-class subscribers."
- **Composition (the paper's thesis):**
  - *turboquant-pro* — compress payloads (embeddings/KV/tensors) on the wire.
  - *batch-probe* — right-size each pod's batch to its GPU (largest that fits, no OOM) +
    thermal-govern the local driver.
- Figure: the burst path with the three tools annotated. (Reuse the README Mermaid diagrams.)

## 4. Evaluation
Three tiers, by infrastructure (mirror `benchmarks/`).
- **4.1 Compression (Tier 1, measured).** Ratios 7.9×/10.4×/15.5× (4/3/2-bit, dim 1024),
  cosine 0.995/0.978/0.94. Transfer of a 1 MB batch: 84→8 ms @100 Mbps (net −63 ms incl.
  encode), ~wash @1 Gbps. **Finding:** compression is a knob; it wins when the *link* is the
  bottleneck (cross-site/WAN bursts), not on a fast LAN. **Real-data check:** real bge-small
  embeddings (20newsgroups, n=3000) reproduce the random-vector ratio+cosine within 0.001 —
  the codec is distribution-agnostic, so the synthetic benchmark is representative.
- **4.2 Transport (Tier 2, measured — loopback *and* real hop).** Loopback: 256-batch
  6.99→1.20 ms p50, ~6×. **Real ~90 ms / ~2 Mbps network hop** (remote workstation → Atlas,
  co-existing on the production bus): the compression win **scales with payload** — 1.2× (4 KB)
  → 3.6× (64 KB) → **8.4× (256 KB)**, converging on the ~10× ratio as the link dominates. This
  *demonstrates* the Tier-1 crossover on a real link, not just on loopback or in the model.
- **4.3 Cluster (Tier 3, measured on NRP).** Ephemeral-Job cold-start: **median ~6.6 s**
  (5.1–7.6 s, n=5), schedule→run ~1–3 s. **Warm-pool + scaling** (N queue-group worker pods,
  driver on Atlas hub, 1 KB tasks): latency **~67 ms** (vs 6.6 s cold start → ~100× overhead
  removed); throughput **plateaus ~930/s by 2 workers** — for trivial I/O tasks the ceiling is
  concurrency÷RTT (Little's law 64/67 ms ≈ 955/s), not worker count (worker-scaling needs a
  compute-bound load). **batch-probe (effective use):** sized an encoder to batch 204 on a GV100
  → **94.4% mean / 100% peak GPU util** at 61 °C (>> NRP's 40%). *Still to run:* true cold image
  pull, GPU-image cold-start, compute-bound scaling.

## 5. Threats to validity (anticipated, with mitigations)
State these explicitly; reviewers will. (Full version in `benchmarks/README.md`.)
- **Synthetic data / cosine proxy (Tier 1):** *addressed* — real bge-small embeddings
  (20newsgroups, n=3000) give identical ratio+cosine to random within 0.001, confirming the
  codec is distribution-agnostic (TurboQuant random-rotation guarantee); cosine is still a
  fidelity proxy, not task quality → don't over-read it.
- **Analytic vs measured transfer (Tier 1):** the WAN-saving table is a model; Tier 2 is the
  real measurement → confirm the crossover on a real link.
- **Loopback (Tier 2):** *addressed* — a real ~2 Mbps hop now shows the win scaling with
  payload (1.2×→3.6×→8.4×); encode cost still excluded (reported in Tier 1) → not free; one
  tailscale path so far, a characterized datacenter link would pin absolute bandwidth.
- **Cold-start realism (Tier 3):** warm node + cached image + `kubectl wait` detection inflate
  the total → report the K8s schedule→run breakdown; *warm-pool (~67 ms) + NATS-join now
  measured*; cold image-pull + GPU-image runs remain.
- **Scaling honesty (Tier 3):** throughput plateaus at ~2 workers because trivial tasks are
  concurrency÷RTT-bound (Little's law), not worker-bound → stated explicitly; compute-bound
  worker-scaling is the named next run, not an overclaim.
- **Small n / single cluster:** report median+range, point-in-time; more reps + replication
  planned; scoped as a practice study, not a universal claim.
- **Cluster citizenship:** policy-safe by construction (ignored-range, ≤1 pod, exit-0 Jobs,
  ttl cleanup, gate flag) — pre-empts the "you abused a shared resource" objection.

## 6. Discussion
- When to compress (link-bound regimes); the encode/transfer crossover.
- "Effective" = batch-probe sizing → high per-pod util (meets NRP's util expectation);
  "policy-safe" = the gate + short runs + cleanup.
- Limitations: single-cluster study; loopback transport numbers; thermal/util are workstation-
  and cluster-specific; not a general scheduler.

## 7. Related work
- Cloud bursting & function/task systems: HTCondor flocking, Globus Compute (funcX), Ray,
  Dask-Jobqueue, Parsl, Covalent.
- Message-bus compute: NATS-based workers; Celery/RabbitMQ task queues (contrast: pods as
  first-class bus subscribers).
- Payload compression for ML transport: gradient/activation compression; embedding/KV-cache
  quantization (turboquant-pro lineage).
- GPU right-sizing / OOM-safe batch search; thermal-aware scheduling (batch-probe lineage).

## 8. Conclusion & availability
- A small, composable, open pipeline that makes a shared cluster usable from the event loop.
- Availability: all three on PyPI (`nats-bursting`, `turboquant-pro`, `batch-probe`) with
  Zenodo DOIs; benchmark harness in-repo (`benchmarks/`); reproducible Tiers 1–2 from committed
  data + scripts.

---

## To do before submission
- ~~Run Tier 3 on NRP — cold-start, warm-pool, scaling, overhead~~ **DONE** (cold ~6.6 s;
  warm-pool ~67 ms; scaling plateaus ~930/s). Remaining: a GPU-image run + GPU-util figure and a
  compute-bound scaling load to show worker-count scaling.
- ~~Re-run Tier 2 over a real network hop~~ **DONE** (remote workstation→Atlas, ~2 Mbps;
  8.4× at 256 KB). Optional: repeat on a characterized datacenter link to pin absolute bandwidth.
- Confirm PEARC (or eScience) deadline + ACM template; recruit a co-author if useful.
- Author/affiliation; reproducibility appendix (commands + commit hashes).
