# An always-on worker pool over NATS, for when vGPU isn't what you actually need

> **TL;DR** — NRP Nautilus gives me a Kubernetes cluster with hundreds of
> idle GPUs, but one-shot Jobs are the wrong shape for many AI workloads:
> the container cold-start eats the task. I extended `nats-bursting` to
> support *persistent worker pools* — N always-on pods subscribed to a
> JetStream work queue, each pulling small tasks as fast as they can
> handle them. It's not vGPU. It's not Ray. It's ~500 lines of Python
> sitting on top of the NATS bus I already had.

## The problem

I'm training an autonomous ARC-AGI agent called **Erebus**. The solve
loop looks like this:

1. Pick an unsolved task.
2. Ask an LLM to write a Python `transform(grid)`.
3. Run it against the examples.
4. If it fails, classify the failure and retry.

Step 2 is ~10 seconds. The LLM call dominates. Running thousands of
these in parallel is embarrassingly parallel — no shared state between
tasks.

My workstation has two Quadro GV100s. I also have access to NRP
Nautilus (~hundreds of shared GPU nodes). NRP's usage policy is real:
no A100s without an access form; 4 heavy pods max, or unlimited
swarm-mode pods at ≤ 1 CPU / ≤ 2 Gi memory. Fair.

## Why vGPU doesn't help here

My first instinct was "GPU virtualization layer." Take one big GPU,
slice it into many vGPUs, run each task on a slice.

That's wrong for two reasons:

- **Access.** vGPU / MIG is a cluster-admin concern. On NRP you don't
  get to configure the GPU operator.
- **Fit.** Even if I could slice, the workload doesn't benefit. The
  bottleneck isn't shared-GPU saturation on one card; it's wall-clock
  latency of many independent LLM calls. What I need is **many small
  workers pulling work in parallel**, not one big GPU sliced N ways.

## Why naïve one-shot Jobs don't help either

`nats-bursting` already supports the "bursting" shape: publish a
`JobDescriptor` on NATS, a Go controller creates a Kubernetes Job in
the remote cluster, the pod joins the NATS fabric, runs, exits. Each
Job is a fresh container: image pull, pip install, bundle clone, model
cache warm-up, then finally your 10-second task.

For tasks that ARE heavy (training a LoRA, inference on a 70B model),
that cold start amortizes. For my 10-second LLM calls, the cold start
dominates. Cluster view: lots of pods churning through bootstrap, a
fraction of wall-clock doing real work.

## The shape I actually wanted

**Persistent workers**, not ephemeral ones. N pods that boot *once*,
pull tasks from a queue forever, ack or nak each one:

```
┌───────── Atlas ────────┐      ┌─── NATS JetStream ───┐      ┌──── NRP (Deployment, N replicas) ───┐
│ TaskDispatcher         │─────►│ stream: TASKS         │─────►│ pod 1   pod 2   pod 3 ... pod N     │
│ .submit_many(tasks)    │      │ subject: tasks.>      │      │  ▲        ▲       ▲         ▲       │
│                        │      │ retention: work-queue │      │  │        │       │         │       │
│                        │◄─────│ subject: results.*    │◄─────│  └── each pulls one task, acks ─┘   │
└────────────────────────┘      └───────────────────────┘      └─────────────────────────────────────┘
```

Three properties I care about:

1. **No cold-start per task.** The pod is already warm; model cache is
   in RAM; just receive → handle → reply.
2. **Built-in load balancing.** JetStream with a work-queue retention
   policy delivers each message to exactly one consumer. Add replicas,
   throughput goes up.
3. **No sleep-to-idle.** When the queue is empty, workers block inside
   `sub.fetch(timeout=30)` — they're in a receive, not in
   `time.sleep`. That matters on NRP because the usage policy
   explicitly forbids Jobs that sleep idle.

## The implementation (~500 LOC)

It turned into a 2-file Python addition to the existing `nats-bursting`
package:

- `PoolDescriptor` — a dataclass that describes the pool (namespace,
  replicas, resources, pre-install commands, entrypoint).
- `pool_manifest(desc)` — renders a Kubernetes Deployment YAML.
- `Worker` / `run_worker(handlers=...)` — the pod-side loop:
  pull one, dispatch on `task.type`, publish result, ack. Crashes
  redeliver automatically; exceptions become structured error results.
- `TaskDispatcher` — Atlas-side async helper that publishes tasks and
  collects results by ID.

Handler contract is deliberately dumb:

```python
from nats_bursting import run_worker

def handle_solve(task):
    # Your 10-second work here.
    return {"status": "solved", "answer": compute(task)}

run_worker(handlers={"solve": handle_solve})
```

That's it. Everything else — NATS connection, JetStream stream
creation, durable pull consumer, ack/nak/redeliver, result publishing,
graceful shutdown — is inside the library.

## NRP-specific design

Two decisions fell out of NRP's usage policy:

- **Swarm mode by default**: `cpu="1"`, `memory="2Gi"` per replica.
  That keeps you in the unlimited-replica tier. I've been running 8
  replicas; could easily scale to dozens without hitting the 4-heavy-
  pod cap.
- **Deployment, not Jobs.** The existing `nats-bursting` creates Jobs
  for the ephemeral shape. Pools use a `Deployment` so pods are
  auto-respawned on crash and can be scaled with `kubectl scale`.

GPU workers are a separate `PoolDescriptor` with `gpu=1`. Because they
request a GPU, they count against the heavy-pod cap — so I limit those
to 4. But I don't need many: the bulk of Erebus's workload is
CPU-only (LLM calls hit an external endpoint, verification is numpy).

## What I did NOT build

- **vGPU.** Not useful. See above.
- **Ray cluster.** Ray gives you distributed Python; I don't need
  distributed Python. I need a durable work queue that both ends
  already speak. NATS already serves messages inside Atlas and inside
  NRP — leveraging it costs nothing.
- **Custom controller.** The existing `nats-bursting` Go controller
  handles submit-and-probe-and-politeness for the ephemeral shape.
  Pools don't need any of that — the Deployment is declarative, no
  controller required.

## What happens when a worker dies

JetStream handles it. The consumer has `ack_wait=300s`. If a worker
pulls a task and then crashes before acking, after 5 minutes the
stream redelivers the task to another worker. No work is lost, no
dispatcher-side bookkeeping.

If a handler raises, the worker publishes `{"error": "...", "traceback":
"..."}` as the result AND nak's the message so JetStream retries. After
`max_deliver=3` attempts the message goes to dead-letter state where
you can inspect it with `nats stream view`.

## What I learned

1. **Name things honestly.** I almost called this a "GPU
   virtualization layer." It isn't. Nobody is slicing a GPU here.
   Calling it what it is — a persistent worker pool — made the design
   obvious.
2. **Use your existing infrastructure.** I already had NATS leafed
   from Atlas into NRP. Adding JetStream and a Deployment on top was
   essentially free. If you don't have a bus yet, add one before you
   think about distributed runtimes.
3. **Pick the shape that matches the workload.** Ephemeral bursts are
   great for 1-hour training runs and terrible for 10-second LLM
   calls. The opposite is true for persistent pools.

## Try it

```bash
pip install 'nats-bursting>=0.2.0'
```

Source + docs: **https://github.com/ahb-sjsu/nats-bursting**
(especially `docs/pools.md` for the deep dive on lifecycle and failure
modes).

Issues, weird use cases, suggestions — all welcome.
