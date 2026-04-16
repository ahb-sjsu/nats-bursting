# nats-bursting design

## Goal

A controller that lets a personal workstation ("Atlas") opportunistically
offload compute jobs to a shared academic Kubernetes cluster (NRP
Nautilus, etc.) without manual `kubectl` ceremony. Conceptually the AI
equivalent of cloud bursting: hot path stays local, cold path bursts.

## Non-goals

- Replacing kubectl for users who already speak Kubernetes
- A general-purpose K8s operator with CRDs and webhooks
- Real-time inference dispatch (Atlas's resident GPUs handle that)

## Architecture

```
   ┌───────── Atlas (workstation) ─────────┐            ┌── NRP (ssu-atlas-ai) ──┐
   │                                       │            │                         │
   │   atlas subsystems publish:           │            │  Workload pods:         │
   │     burst.submit { JobDescriptor }    │            │   - subscribe agi.*     │
   │     agi.lh.request.*  etc.            │            │   - publish responses   │
   │                                       │            │     as if local         │
   │   NATS hub :4222  ◄─── leaf link ─────────────────►│                         │
   │                       (TLS, :7422)    │            │  NATS leaf pod          │
   │                                       │            │   bridges subjects      │
   │   nats-bursting (Go binary):            │            │   into the namespace    │
   │     1. consume burst.submit           │            │                         │
   │     2. probe k8s state                │            │  nats-bursting creates    │
   │     3. politeness decision            │ kubeconfig │  Jobs via K8s API       │
   │     4. client-go Job create  ──────────────────►   │                         │
   │     5. publish burst.status.<id>      │            │                         │
   └───────────────────────────────────────┘            └─────────────────────────┘
```

### Components

* **`internal/decider`** — pure function `Decide(state, politeness)
  → (Submit | Backoff | Abort, reason)`. Same priority order as
  `polite-submit` Python: self-limit → courtesy → utilization.
* **`internal/backoff`** — exponential-with-jitter wait scheduler.
* **`internal/prober`** — `client-go` reads of nodes / jobs /
  cluster-wide pending pods. Each call degrades gracefully if the
  caller lacks the RBAC for it.
* **`internal/submitter`** — turns a `JobDescriptor` (small, NATS-
  shipped struct) into a real `*batchv1.Job` and creates it.
* **`internal/natsbridge`** — NATS `Subscribe(burst.submit)` →
  `Submitter.Submit` → `Publish(burst.status.<id>)`.
* **`cmd/nats-bursting/main.go`** — config load, k8s client init,
  signal handling, run loop.

### JobDescriptor

The minimum useful contract for a NATS submit message:

```go
type JobDescriptor struct {
    Name      string
    Image     string
    Command   []string
    Args      []string
    Env       map[string]string
    Resources Resources
    Labels    map[string]string
    BackoffLimit int32
}

type Resources struct {
    CPU              string
    Memory           string
    GPU              int32
    EphemeralStorage string
}
```

Anything more elaborate (volume mounts, init containers, sidecars)
should publish multiple JobDescriptors or use a richer custom
resource — out of scope for v1.

### Why a dedicated controller (vs. just publishing YAML)

* **Politeness** — the cluster's 400-pod cap and shared utilization
  pressure make naive `kubectl apply` floods rude. Controller
  centralizes the decision.
* **State management** — Atlas subsystems care about job lifecycle
  events, not raw K8s API watches. Controller maps watch streams to
  per-job NATS topics.
* **Auth boundary** — only the controller needs a Nautilus
  kubeconfig; Atlas subsystems just publish on a local NATS bus.

## Threat model

* Atlas's NATS bus is extended to NRP via a NATS **leaf node**
  connection (outbound from NRP, TLS terminated by nats-server itself
  using Caddy-managed Let's Encrypt certs, exposed publicly through
  DuckDNS + home-router NAT on port 7422). NATS user/password auth
  guards the leaf endpoint. See `docs/nats-leafnode-duckdns.md`.
* The NATS subject namespace is unscoped: anyone with leaf credentials
  can publish `burst.submit` or any `agi.*` subject the leaf is
  configured to propagate. Single-user system today; multi-tenant
  requires account-based isolation (separate NATS account per tenant
  with explicit subject exports) and eventually per-user subject
  prefixes.

## Scaling notes

* The controller is single-process. For high throughput, multiple
  controllers can subscribe via a JetStream pull consumer and let
  NATS load-balance.
* `client-go`'s informer cache could replace the periodic prober
  later for sub-second freshness, at the cost of memory. Current
  on-demand probing is fine for the bursting cadence (job submission
  is usually seconds or minutes apart).
