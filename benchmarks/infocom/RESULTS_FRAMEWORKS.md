# Framework comparison — same-node warm-pool dispatch + throughput

Same GV100, same workload (MiniLM embedding of batches), 4 warm workers, model
preloaded per worker. Isolates **fabric/dispatch overhead** — NOT the WAN/cluster
path or multi-tenant fair-use policy (only nats-bursting has those, by design).

| fabric | dispatch p50 | dispatch p99 | embed thr. (batch-64) | warm setup |
|---|---|---|---|---|
| `ProcessPoolExecutor` | 1.0 ms | 1.3 ms | 9000 docs/s | 9.6 s |
| **nats-bursting** | **1.3 ms** | 51.7 ms | 920 docs/s | 10.4 s |
| Ray | 2.3 ms | 2.8 ms | 9800 docs/s | 16.2 s |
| Dask | 13.9 ms | 90.0 ms | 1050 docs/s | 10.8 s |
| Parsl (HTEx) | — | — | — | by design¹ |
| funcX / Globus Compute | — | — | — | by design² |

¹ Parsl HTEx interchange failed to launch in the isolated venv; characterized by design.
² funcX needs a hosted, Globus-authenticated endpoint; out of scope, characterized by design.

**Reading.** nats-bursting's dispatch latency is competitive — 2nd, between
`ProcessPool` and Ray, ~10× under Dask. On throughput, the in-process engines
(Ray, ProcessPool) reach the GPU-bound ceiling (~9k docs/s) while the
message-oriented fabrics (Dask, nats-bursting) pay a per-task messaging cost on
fine-grained tasks — which is why the pool dispatches **batches** in practice. The
differentiator is not raw speed but capability: a host **politeness budget**, an
**inbound-restricted WAN leaf-federation**, and a burst that is a **publish inside
the event loop** — none of which the general task engines carry. Positioning, not a
leaderboard.

**Honest scope.** Same-node fabric overhead only; the p99 tails for the
message-bus fabrics (Dask, nats-bursting) reflect async/GC jitter. Repro: isolated
venv (`python3 -m venv /tmp/benchvenv` + a `.pth` to the base venv's site-packages
for the driver-matched torch/cu128; `pip install 'ray[default]' 'dask[distributed]'
parsl nats-py`), then `bench_frameworks.py --framework {processpool,ray,dask}` and
`bench_nats_pool.py --role driver`. GPU pinned to the free GV100.
