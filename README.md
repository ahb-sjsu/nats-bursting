# atlas-burst

[![CI](https://github.com/ahb-sjsu/atlas-burst/actions/workflows/ci.yml/badge.svg)](https://github.com/ahb-sjsu/atlas-burst/actions/workflows/ci.yml)
[![Go Report](https://goreportcard.com/badge/github.com/ahb-sjsu/atlas-burst)](https://goreportcard.com/report/github.com/ahb-sjsu/atlas-burst)

**AI bursting controller** — listens on a NATS queue for compute job
requests from a workstation ("Atlas") and dispatches them to a remote
Kubernetes cluster ("Nautilus") with built-in politeness backoff.

## What it does

`atlas-burst` is the bridge between an always-on personal workstation
running cognitive workloads (e.g. local LLMs, real-time inference)
and an elastic shared HPC Kubernetes cluster. It implements **AI
bursting** — the AI equivalent of cloud bursting:

- **Hot path stays local**: latency-sensitive cognition runs on
  Atlas's resident GPUs.
- **Cold path bursts to Nautilus**: training runs, parameter sweeps,
  bulk inference, and any workload that doesn't fit Atlas's 2× GV100
  ceiling.

The controller subscribes to NATS subjects
(`burst.submit.*`, `burst.cancel.*`), translates incoming
`JobDescriptor` messages into Kubernetes Job manifests, applies them
via `client-go`, and streams status events back as NATS messages
(`burst.status.<job_id>`, `burst.result.<job_id>`).

## Why Go

- `client-go` is the canonical Kubernetes client; using it natively
  avoids subprocess overhead and gives type-safe access.
- Single static binary with no runtime dependencies — easy to embed
  in container images and ship as a systemd service.
- Matches the Kubernetes ecosystem convention.

## Politeness

`atlas-burst` reuses the CSMA/CA-inspired politeness model from
[polite-submit](https://github.com/ahb-sjsu/polite-submit). Before
each submission it probes:

- Number of your own running / pending Jobs in your namespace
- Cluster-wide pending pod count (queue pressure)
- Per-node CPU utilization

…and backs off exponentially when any threshold is exceeded. The same
politeness logic ports cleanly across schedulers (Slurm via
polite-submit, Kubernetes via atlas-burst).

## Status

This repo is in **bootstrap**. See `docs/design.md` for the full
architecture; the `internal/` packages are scaffolds with stub
implementations. First milestone: trivial Job submission via NATS
publish, status echo back via NATS subscribe.

## Architecture

```
                                Tailscale Funnel
   ┌─────────────────┐         (public NATS endpoint)         ┌────────────────────────┐
   │      Atlas      │                                        │  Nautilus K8s pod      │
   │  (workstation)  │ ──────► nats://atlas-funnel:4222 ◄──── │  - atlas-burst worker  │
   │                 │                                        │  - your job            │
   │  publishes:     │                                        │                        │
   │  burst.submit   │                                        │  publishes:            │
   │  consumes:      │                                        │  burst.status.<id>     │
   │  burst.status.* │                                        │  burst.result.<id>     │
   └─────────────────┘                                        └────────────────────────┘
```

## Quick Start (once it's built)

```bash
# As a controller running on Atlas (submits to Nautilus)
atlas-burst controller \
  --nats nats://localhost:4222 \
  --kubeconfig ~/.kube/nautilus.yaml \
  --namespace your-ns

# As an in-pod runner inside a Nautilus Job (publishes status back)
atlas-burst runner \
  --nats nats://atlas-funnel:4222 \
  --job-id "$JOB_ID"
```

## Requirements

- Go 1.23+
- A reachable NATS server (e.g. via Tailscale Funnel — see
  `docs/tailscale-funnel.md`)
- A Kubernetes cluster you have a kubeconfig for (e.g. NRP Nautilus)

## License

MIT
