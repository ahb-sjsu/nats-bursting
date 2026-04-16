# I built cloud bursting for AI workloads that runs over a NATS bus, and it changed how I think about hybrid compute

*Draft for LinkedIn — ~600 words, conversational register. Tag: ML infrastructure, Kubernetes, NATS, HPC.*

---

A single-workstation AI researcher runs into the same wall everyone does
eventually: your local GPUs are great for real-time inference but useless
for a 72B fine-tune. You have access to a shared academic Kubernetes
cluster (NRP Nautilus, in my case), but every time you want to burst a
job, you're context-switching out of your research flow to write YAML,
`kubectl apply`, tail logs, and clean up afterwards.

The standard answer is a job-queue service — something like Ray, or a
REST API in front of the cluster. I already run NATS JetStream as the
event fabric for my cognitive architecture on Atlas (my workstation).
Standing up a second queue *just* for bursting felt wrong. So I extended
the bus I already have.

**`nats-bursting`** (
[github.com/ahb-sjsu/nats-bursting](https://github.com/ahb-sjsu/nats-bursting)
) is a small Go controller that subscribes to a `burst.submit` subject
on my local NATS server. When a JobDescriptor message lands, it:

1. Probes the remote cluster's state (my own queue depth, cluster-wide
   pending pods, per-node CPU)
2. Applies a CSMA/CA-inspired **politeness backoff** — if the cluster
   is busy, it waits exponentially rather than flooding
3. Translates the JobDescriptor into a Kubernetes Job via `client-go`
4. Publishes status events back onto NATS

The crucial insight, and the reason this is different from every
"cloud bursting 101" blog post: the remote cluster **doesn't run a
dispatcher at all**. A single `nats-server` pod in my namespace runs
as a NATS leaf node — it dials outbound over TLS to my workstation's
public hostname (DuckDNS + router NAT port-forward) and bridges
subjects bidirectionally. Remote pods subscribe to `agi.memory.query.*`
and publish responses just as if they were running locally.

One protocol end-to-end. No custom webhooks. No REST API. No sidecars.
No Tailscale agent in the pod (which NRP blocks anyway — no NET_ADMIN).

```python
%load_ext nats_bursting.magic

%%burst --gpu 1 --memory 24Gi
import torch
model = load_qwen_72b()
model.generate(prompt)
```

The `%%burst` cell magic checks `nvidia-smi` first — if my local Quadro
GV100 has headroom, the cell runs locally. If it's saturated, the cell
packages itself into a JobDescriptor and ships. First job ran end-to-end
in 23 minutes from idea to deployed, on a pod at the San Diego
Supercomputer Center that I'd never `kubectl`-ed to directly.

**Three things I was surprised by:**

1. **Leaf-node connections are the right abstraction.** I went in
   assuming I'd need Tailscale Funnel or a Matrix bridge. Neither was
   needed. NATS has had leaf nodes since 2.2 and they're exactly this
   use case — a remote "spoke" that participates in the hub's subject
   space over a single outbound TLS connection.

2. **Politeness is a feature, not a hack.** Academic clusters have
   hard caps (400-pod namespace limit on NRP) and soft social contracts
   ("don't flood during business hours"). A controller that *knows*
   these thresholds and backs off gracefully is strictly better than
   per-user etiquette.

3. **The workstation never opens an inbound port.** Between NAT on the
   Kubernetes pod side and outbound-only TLS leaf dialing, the threat
   model is much narrower than the equivalent HTTP dispatcher would be.

Shipping `nats-bursting` as a PyPI package + Go binary, MIT license.
If you run NATS for anything else and have an academic K8s allocation
sitting idle, the whole integration is one `pip install` + one Go
binary + a kustomize apply. Would love feedback.

#MachineLearning #Kubernetes #NATS #HPC #OpenSource

---

*Links:*
- *Repo: https://github.com/ahb-sjsu/nats-bursting*
- *Related: https://github.com/ahb-sjsu/polite-submit (the Slurm-side
  politeness engine that this Kubernetes-side borrows from)*
