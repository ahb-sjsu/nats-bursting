# Reddit post drafts

Two drafts: one for `r/MachineLearning`, one for `r/kubernetes`. Each
targets a slightly different audience so the framing differs.

---

## Draft for r/kubernetes

**Title:** `[P] nats-bursting: treat a shared K8s cluster as an extension of your local NATS bus (politeness backoff included)`

**Body:**

Ran into a dead end with the usual cloud-bursting patterns and built
this instead. Posting here because I'd like feedback on the K8s side of
the architecture — whether the NATS leaf approach is a better fit than
the usual "REST dispatcher in front of the API server" pattern.

**The problem:** single-workstation researcher (2× GV100 32GB) with
access to NRP Nautilus. Want to burst training runs to NRP without
leaving my local workflow. I already run NATS JetStream for inter-
service coordination locally. Setting up a second queue for
bursting felt redundant.

**The solution:** extend the NATS bus into the remote namespace.

- A `nats-server` pod runs in my NRP namespace as a **leaf node**. It
  dials outbound over TLS to my workstation's public endpoint
  (DuckDNS + home router NAT port-forward on 7422).
- Workload pods in the namespace connect to the in-cluster leaf
  service and subscribe to whatever subjects they care about.
- Subjects bridge bidirectionally. A pod publishing
  `agi.memory.query.response` lands on my workstation's NATS just as
  if the pod were local.
- A small Go controller on my workstation listens on `burst.submit`
  and translates `JobDescriptor` messages into K8s Jobs via
  `client-go`, with CSMA/CA-inspired politeness backoff (probes queue
  depth, cluster-wide pending pods, per-node utilization before each
  submit).

No Tailscale agent in the pod (NRP blocks NET_ADMIN anyway). No Matrix
or webhooks. One protocol end-to-end. No inbound port on the
workstation.

Two things I want sanity checks on:

1. **Leaf nodes vs Gateways.** I picked leafs because this is a
   hub-and-spoke pattern with one hub. A gateway would make more sense
   if I wanted bidirectional cluster-to-cluster. Am I missing a reason
   gateway would still be better here?

2. **Politeness defaults.** I'm capping at 10 concurrent + 5 pending
   Jobs with a 0.85 cluster utilization threshold and 30s→15min
   exponential backoff. Feels conservative for NRP's 400-pod namespace
   cap but I'd rather be too polite than too rude on a shared
   resource. Feedback welcome from anyone who's been on the NRP
   admin side.

Repo: https://github.com/ahb-sjsu/nats-bursting

Python client on PyPI as `nats-bursting`. Go controller builds to a
~44MB static binary. Full kustomize base for the remote side in
`deploy/kubernetes/nrp/`. Leaf-node runbook in
`docs/nats-leafnode-duckdns.md`.

First end-to-end burst ran today — Python cell on Windows published a
JobDescriptor to my workstation's NATS, controller applied the Job on
NRP, pod scheduled on an SDSC node, logs came back. Shipping as MIT.

---

## Draft for r/MachineLearning

**Title:** `[P] Opportunistic cloud bursting for ML workloads over a NATS event bus (AI-native hybrid compute)`

**Body:**

TL;DR — if your workstation already speaks NATS, you can extend that
bus into a remote Kubernetes cluster and treat the cluster as elastic
extra GPU capacity without any separate dispatcher, webhook, or REST
API. [`nats-bursting`](https://github.com/ahb-sjsu/nats-bursting) is
the glue: one PyPI package + one Go binary + one kubectl apply.

**Why this vs. existing patterns:**

- *Ray / Modal / Beam*: great if you start greenfield, heavy if you
  already have a message bus doing other work.
- *REST API + custom dispatcher*: duplicates queue infra, parallel
  latency path.
- *`kubectl apply` in a notebook cell*: doesn't compose with async
  inference loops, no politeness.

**What this is instead:**

```python
%load_ext nats_bursting.magic

%%burst --gpu 1 --memory 24Gi
import torch
model = load_qwen_72b()
model.generate(prompt)
```

The cell checks `nvidia-smi`. If my local GV100 has headroom, the cell
runs locally. If saturated, it packages itself into a `JobDescriptor`,
publishes to `burst.submit` on my local NATS, and a Go controller
applies it as a K8s Job on NRP Nautilus.

**The interesting piece** is bidirectional subject bridging. A NATS
leaf-node pod in my remote namespace dials outbound to my workstation
over TLS. Remote pods then subscribe to `agi.memory.query.*` and
publish responses as first-class participants in the event fabric.
When my local memory service is saturated, a burst pod running the
same handler picks up the slack transparently.

**Politeness is built in.** Before each Job creation, the controller
probes:

- Own running + pending Jobs in namespace
- Cluster-wide pending pods (queue pressure)
- Per-node CPU utilization

…and exponentially backs off when shared thresholds are exceeded.
Inspired by CSMA/CA. Academic shared clusters have 400-pod caps and
soft fairness contracts — this respects both.

**Status:** end-to-end path proven today. Python cell → local NATS →
controller → client-go → NRP → pod on SDSC → logs returned. PyPI
release next. Looking for feedback from anyone with similar hybrid
workstation/cluster setups, especially on politeness tuning and where
the NATS subject namespace could be tightened for multi-tenant.

Repo: https://github.com/ahb-sjsu/nats-bursting
Related Slurm-side politeness: https://github.com/ahb-sjsu/polite-submit
MIT license.
