# Short systems paper — outline

**Working title:** *Bursting AI Workloads to a Shared Cluster over NATS: A Compression- and
GPU-Aware Pipeline for Effective, Policy-Safe Use of NRP Nautilus*

**Target:** PEARC (Practice & Experience in Advanced Research Computing) — short/technical
paper, ACM format, ~6 pp. Alt: IEEE eScience short paper, or an SC workshop (workflows/clouds).
Audience: the ACCESS/NRP research-computing community that already lives this pain.

**Status:** Tiers 1–2 + Tier-3 cold-start have real numbers (committed in `benchmarks/`); the
remaining Tier-3 modes (warm-pool, scaling, overhead, GPU-util) are the open runs. A
threats-to-validity section (§5) anticipates the reviewer objections.

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
  bottleneck (cross-site/WAN bursts), not on a fast LAN.
- **4.2 Transport (Tier 2, measured on Atlas).** NATS round-trip + throughput, raw vs
  compressed, per payload size: 256-batch 6.99→1.20 ms p50, 137→783 msgs/s (~6×). Payload size
  dominates round-trip even on loopback.
- **4.3 Cluster (Tier 3, cold-start measured on NRP).** Ephemeral CPU-Job cold-start
  (ignored-range, one pod at a time, auto-cleaned): submit→complete **median ~6.6 s**
  (5.1–7.6 s, n=5), pod schedule→container-start ~1–3 s. *Still to run:* warm-pool latency,
  throughput vs N replicas (JetStream backpressure), burst-path vs raw-`kubectl` overhead, and
  GPU utilization with batch-probe sizing — all policy-gated, short, cleaned-up.

## 5. Threats to validity (anticipated, with mitigations)
State these explicitly; reviewers will. (Full version in `benchmarks/README.md`.)
- **Synthetic data / cosine proxy (Tier 1):** random vectors + cosine is a fidelity proxy,
  not task quality → rerun on real embeddings; don't over-read cosine.
- **Analytic vs measured transfer (Tier 1):** the WAN-saving table is a model; Tier 2 is the
  real measurement → confirm the crossover on a real link.
- **Loopback (Tier 2):** understates compression → conservative lower bound; encode cost
  excluded from the loop (reported in Tier 1) → not free; real workstation→NRP hop planned.
- **Cold-start realism (Tier 3):** warm node + cached image + `kubectl wait` detection inflate
  the total → report the K8s schedule→run breakdown; cold-pull + GPU-image + NATS-join runs
  planned.
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
- Run Tier 3 on NRP (short, policy-checked) → fill §4.3 with real cold-start / warm-pool /
  scaling / overhead numbers + a GPU-util figure.
- Re-run Tier 2 over a *real network hop* (workstation→NRP), not just loopback, to show the
  compression crossover on a production link.
- Confirm PEARC (or eScience) deadline + ACM template; recruit a co-author if useful.
- Author/affiliation; reproducibility appendix (commands + commit hashes).
