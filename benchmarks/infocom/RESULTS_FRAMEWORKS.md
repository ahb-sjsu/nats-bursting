# Framework comparison — same-node warm-pool dispatch + throughput

Same GV100, same workload (MiniLM embedding of batches), 4 warm workers, model
preloaded per worker. Isolates **fabric/dispatch overhead** — NOT the WAN/cluster
path or multi-tenant fair-use policy (only nats-bursting has those, by design).

**Dispatch latency (the fair metric — tiny warm round-trip):**

| fabric | dispatch p50 | dispatch p99 | warm setup |
|---|---|---|---|
| `ProcessPoolExecutor` | 1.0 ms | 1.3 ms | 9.6 s |
| **nats-bursting** | **1.1 ms** | ~52 ms | 10.4 s |
| Ray | 2.3 ms | 2.8 ms | 16.2 s |
| Dask | 13.9 ms | 90.0 ms | 10.8 s |
| Parsl (HTEx) | — | — | by design¹ |
| funcX / Globus Compute | — | — | by design² |

¹ Parsl HTEx interchange failed to launch in the isolated venv; characterized by design.
² funcX needs a hosted, Globus-authenticated endpoint; out of scope, characterized by design.

**Reading.** nats-bursting's dispatch latency is competitive — on par with
`ProcessPool`, under Ray, ~10× below Dask; its tail is looser (async/GC jitter). The
differentiator is not raw speed but capability: a host **politeness budget**, an
**inbound-restricted WAN leaf-federation**, and a burst that is a **publish inside
the event loop** — none of which the general task engines carry. Positioning, not a
leaderboard.

**Throughput — root-caused and fixed with a Go driver.** An earlier Python `asyncio`
driver reported nats-bursting at 920 docs/s and, tellingly, it did **not** scale with
workers (W=1/2/4 → 870/867/957) and moving the encode off the event loop didn't help
— the bottleneck was the single-client Python driver, not the bus. Re-driving the
same Python GPU workers from Go (`nats.go`, the client nats-bursting's control plane
already uses; `natsbench/`) confirms it:

| workers | tiny (pure fabric) | embed (real AI work) |
|---|---|---|
| 1 | 8036 req/s | 2421 docs/s |
| 2 | 9106 req/s | 4461 docs/s |
| 4 | 8264 req/s | **9407 docs/s** |
| 8 | 10423 req/s | 14906 docs/s |

The fabric sustains **~8–10k req/s** on near-empty tasks (so the bus was never the
limit), and embedding throughput **scales with workers** to the GPU-bound ceiling
(9.4k docs/s at 4 workers — competitive with Ray 9.8k / ProcessPool 9.0k, far above
Dask 1.05k; disp p50 0.9 ms). The Python-driver number was a ~10× harness artifact
and is retracted. Orchestration: `run_gonats.sh` (nats-server + Python GPU workers +
Go driver).

**Compute-bound scaling** (`bench_embed_scaling.py`; MiniLM, warm workers across
both GV100s):

| workers | throughput | speedup |
|---|---|---|
| 1 | 8,067 docs/s | 1.0× |
| 2 | 14,640 docs/s | 1.8× |
| 4 | 29,317 docs/s | 3.6× |
| 6 | 41,542 docs/s | 5.1× |
| 8 | 43,792 docs/s | 5.4× (2-GPU saturation) |

Throughput scales with parallelism until the two GPUs saturate (~44k docs/s) — the
compute-bound counterpart to the I/O-bound warm-pool plateau (~930/s at 2 workers,
Little's law). Figure: `../../paper/figures/embed_scaling.pdf`.

**Repro.** Isolated venv (`python3 -m venv /tmp/benchvenv` + a `.pth` to the base
venv's site-packages for driver-matched torch/cu128; `pip install 'ray[default]'
'dask[distributed]' parsl nats-py`), then `bench_frameworks.py --framework
{processpool,ray,dask}` and `bench_nats_pool.py --role driver`. Scaling uses the
base venv directly. GPUs: dispatch on the free GV100; scaling across both.
