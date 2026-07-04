"""nats-bursting warm-pool arm of the framework comparison (same metrics/schema as
bench_frameworks.py): a local nats-server + W queue-group worker processes, each
with MiniLM preloaded on cuda:1. Driver measures dispatch latency (tiny task
request/reply) and embedding throughput. Same-node, warm -- isolates the bus
fabric's overhead against Ray/Dask/ProcessPool.

  driver:  python bench_nats_pool.py --role driver --workers 4 --out fw_nats.json
  worker:  (spawned by the driver) --role worker --url ... --subj ... --ready ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")
os.environ.setdefault("HF_HOME", "/archive/cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NATS_BIN = "/home/claude/bin/nats-server"


def _pctl(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * (len(xs) - 1)))]


async def worker(url, subj, ready):
    import nats
    import torch
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MODEL, device="cuda")
    warm = torch.ones(8, 8, device="cuda")
    nc = await nats.connect(url)

    async def handler(msg):
        p = msg.data.decode()
        if p == "tiny":
            (warm @ warm).sum().item()
            r = b"1"
        else:
            n = int(p.split(":")[1])
            m.encode(["the quick brown fox jumps over the lazy dog"] * n,
                     batch_size=min(n, 128), convert_to_numpy=True)
            r = str(n).encode()
        await nc.publish(msg.reply, r)

    await nc.subscribe(subj, queue="pool", cb=handler)
    await nc.publish(ready, b"1")
    await nc.flush()
    while True:
        await asyncio.sleep(3600)


async def driver(a):
    import nats
    port = 4300
    url = f"nats://127.0.0.1:{port}"
    srv = subprocess.Popen([NATS_BIN, "-p", str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    t0 = time.time()
    nc = await nats.connect(url)
    ready_count = [0]

    async def _r(msg):
        ready_count[0] += 1
    await nc.subscribe("ready", cb=_r)

    workers = [subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--role", "worker",
         "--url", url, "--subj", "task", "--ready", "ready"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(a.workers)]
    while ready_count[0] < a.workers and time.time() - t0 < 180:
        await asyncio.sleep(0.2)
    setup = time.time() - t0

    lat = []
    for _ in range(a.ntiny):
        s = time.time()
        await nc.request("task", b"tiny", timeout=10)
        lat.append((time.time() - s) * 1e3)

    t = time.time()
    payload = f"embed:{a.batch}".encode()
    done = 0
    # keep the pool saturated: a sliding window of in-flight requests
    inflight = set()
    sent = 0
    while done < a.nembed:
        while len(inflight) < a.workers * 6 and sent < a.nembed:
            inflight.add(asyncio.create_task(nc.request("task", payload, timeout=30)))
            sent += 1
        d, inflight = await asyncio.wait(inflight, return_when=asyncio.FIRST_COMPLETED)
        for f in d:
            done += int(f.result().data.decode())
    thr = done / (time.time() - t)

    for w in workers:
        w.terminate()
    await nc.close()
    srv.terminate()
    res = {
        "framework": "nats-bursting", "setup_s": round(setup, 2),
        "dispatch_p50_ms": round(_pctl(lat, 50), 2),
        "dispatch_p99_ms": round(_pctl(lat, 99), 2),
        "embed_throughput_docs_s": round(thr, 1),
    }
    json.dump(res, open(a.out, "w"), indent=2)
    print(f"[bench] nats-bursting: setup={res['setup_s']}s dispatch "
          f"p50={res['dispatch_p50_ms']}ms p99={res['dispatch_p99_ms']}ms "
          f"embed={res['embed_throughput_docs_s']} docs/s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["driver", "worker"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--ntiny", type=int, default=60)
    ap.add_argument("--nembed", type=int, default=120)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--out", default="/tmp/e9/fw_nats.json")
    ap.add_argument("--url"); ap.add_argument("--subj"); ap.add_argument("--ready")
    a = ap.parse_args()
    if a.role == "worker":
        asyncio.run(worker(a.url, a.subj, a.ready))
    else:
        asyncio.run(driver(a))


if __name__ == "__main__":
    main()
