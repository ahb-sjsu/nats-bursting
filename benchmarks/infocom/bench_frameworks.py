"""Same-node, same-workload warm-pool comparison of task fabrics on one GV100.

Frameworks: raw ProcessPool, Ray, Dask, Parsl, and the nats-bursting NATS warm
pool. Two metrics per fabric, all workers warm (model preloaded):
  (1) dispatch latency  -- tiny warm GPU task round-trip (isolates fabric overhead)
  (2) embedding throughput -- MiniLM batch embedding (real GPU AI work; GPU-bound)

HONEST SCOPE: this is same-node fabric/dispatch overhead on identical hardware and
workload -- NOT the cross-site WAN path or multi-tenant fair-use policy, which only
nats-bursting addresses by design. funcX/Globus Compute needs an authenticated
hosted endpoint and is out of scope here (characterized by design, not measured).

Run with /tmp/benchvenv (inherits torch, adds ray/dask/parsl/nats-py). GPU pinned
to cuda:1 (free). One framework per invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")
os.environ.setdefault("HF_HOME", "/archive/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_M = None


def get_model():
    global _M
    if _M is None:
        from sentence_transformers import SentenceTransformer
        _M = SentenceTransformer(MODEL, device="cuda")
    return _M


def embed_task(n):
    m = get_model()
    m.encode(["the quick brown fox jumps over the lazy dog"] * n,
             batch_size=min(n, 128), convert_to_numpy=True)
    return n


def tiny_task(_):
    import torch
    x = torch.ones(8, 8, device="cuda")
    (x @ x).sum().item()
    return 1


def _pctl(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * (len(xs) - 1)))]


def summarize(name, setup_s, lat_ms, thr_docs_s):
    return {
        "framework": name,
        "setup_s": round(setup_s, 2),
        "dispatch_p50_ms": round(_pctl(lat_ms, 50), 2),
        "dispatch_p99_ms": round(_pctl(lat_ms, 99), 2),
        "embed_throughput_docs_s": round(thr_docs_s, 1),
    }


# ---------------------------------------------------------------- ProcessPool
def run_processpool(W, ntiny, nembed, batch):
    from concurrent.futures import ProcessPoolExecutor
    t = time.time()
    ex = ProcessPoolExecutor(max_workers=W, initializer=get_model)
    list(ex.map(tiny_task, range(W)))  # warm up all workers
    setup = time.time() - t
    lat = []
    for _ in range(ntiny):
        s = time.time(); next(iter([ex.submit(tiny_task, 0).result()])); lat.append((time.time() - s) * 1e3)
    t = time.time()
    done = sum(ex.map(embed_task, [batch] * nembed))
    thr = done / (time.time() - t)
    ex.shutdown()
    return summarize("processpool", setup, lat, thr)


# ------------------------------------------------------------------------ Ray
def run_ray(W, ntiny, nembed, batch):
    import ray
    t = time.time()
    ray.init(num_gpus=1, num_cpus=W + 2, include_dashboard=False,
             ignore_reinit_error=True, log_to_driver=False,
             runtime_env={"env_vars": {"CUDA_VISIBLE_DEVICES": "0",
                                       "HF_HOME": os.environ["HF_HOME"],
                                       "HF_HUB_OFFLINE": "1"}})

    @ray.remote(num_gpus=1.0 / W)
    class Worker:
        def __init__(self):
            get_model()
        def tiny(self, _):
            return tiny_task(0)
        def embed(self, n):
            return embed_task(n)

    workers = [Worker.remote() for _ in range(W)]
    ray.get([w.tiny.remote(0) for w in workers])  # warm
    setup = time.time() - t
    lat = []
    for i in range(ntiny):
        s = time.time(); ray.get(workers[i % W].tiny.remote(0)); lat.append((time.time() - s) * 1e3)
    t = time.time()
    futs = [workers[i % W].embed.remote(batch) for i in range(nembed)]
    done = sum(ray.get(futs))
    thr = done / (time.time() - t)
    ray.shutdown()
    return summarize("ray", setup, lat, thr)


# ----------------------------------------------------------------------- Dask
def run_dask(W, ntiny, nembed, batch):
    from dask.distributed import Client, LocalCluster
    t = time.time()
    cluster = LocalCluster(n_workers=W, threads_per_worker=1, processes=True,
                           dashboard_address=None)
    client = Client(cluster)
    client.run(lambda: (get_model(), True)[1])  # warm every worker (don't return model)
    setup = time.time() - t
    lat = []
    for _ in range(ntiny):
        s = time.time(); client.submit(tiny_task, 0, pure=False).result(); lat.append((time.time() - s) * 1e3)
    t = time.time()
    futs = client.map(embed_task, [batch] * nembed, pure=False)
    done = sum(client.gather(futs))
    thr = done / (time.time() - t)
    client.close(); cluster.close()
    return summarize("dask", setup, lat, thr)


# ---------------------------------------------------------------------- Parsl
def run_parsl(W, ntiny, nembed, batch):
    import parsl
    from parsl.app.app import python_app
    from parsl.config import Config
    from parsl.executors import HighThroughputExecutor
    from parsl.providers import LocalProvider
    t = time.time()
    parsl.load(Config(run_dir="/tmp/e9/parsl_runinfo", executors=[HighThroughputExecutor(
        label="local", max_workers_per_node=W, address="127.0.0.1",
        provider=LocalProvider(init_blocks=1, max_blocks=1))]))

    @python_app
    def p_tiny(_):
        import bench_frameworks as bf
        return bf.tiny_task(0)

    @python_app
    def p_embed(n):
        import bench_frameworks as bf
        return bf.embed_task(n)

    [p_tiny(i).result() for i in range(W)]  # warm
    setup = time.time() - t
    lat = []
    for _ in range(ntiny):
        s = time.time(); p_tiny(0).result(); lat.append((time.time() - s) * 1e3)
    t = time.time()
    done = sum(f.result() for f in [p_embed(batch) for _ in range(nembed)])
    thr = done / (time.time() - t)
    parsl.dfk().cleanup()
    return summarize("parsl", setup, lat, thr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", required=True,
                    choices=["processpool", "ray", "dask", "parsl"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--ntiny", type=int, default=100)
    ap.add_argument("--nembed", type=int, default=200)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fn = {"processpool": run_processpool, "ray": run_ray, "dask": run_dask,
          "parsl": run_parsl}[a.framework]
    res = fn(a.workers, a.ntiny, a.nembed, a.batch)
    json.dump(res, open(a.out, "w"), indent=2)
    print(f"[bench] {res['framework']}: setup={res['setup_s']}s "
          f"dispatch p50={res['dispatch_p50_ms']}ms p99={res['dispatch_p99_ms']}ms "
          f"embed={res['embed_throughput_docs_s']} docs/s", flush=True)


if __name__ == "__main__":
    main()
