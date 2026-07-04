"""nats-bursting warm-pool arm of the framework comparison. A local nats-server + W
queue-group worker processes, each with MiniLM preloaded on cuda:1. Driver measures
per-task dispatch latency (sequential round-trip) and saturated throughput
(bounded-concurrency gather) for a tiny task (isolates the bus) or an embed task.

Concurrency fixes vs. the first draft: (1) each worker schedules the task as a
background coroutine instead of blocking its subscription (nats-py otherwise awaits
each callback serially -> one in-flight per worker); (2) the throughput driver uses a
semaphore-bounded gather rather than a hand-rolled sliding window.

  driver:  python bench_nats_pool.py --role driver --workers 4 --task embed --out ...
  worker:  (spawned) --role worker --url ... --subj task --ready ready
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
    loop = asyncio.get_event_loop()
    nc = await nats.connect(url)
    sem = asyncio.Semaphore(8)  # cap concurrent encodes/worker (GPU serialises anyway)

    def _encode(n):
        m.encode(["the quick brown fox jumps over the lazy dog"] * n,
                 batch_size=min(n, 128), convert_to_numpy=True)

    async def _process(msg):
        p = msg.data.decode()
        if p == "tiny":
            (warm @ warm).sum().item()
            r = b"1"
        else:
            n = int(p.split(":")[1])
            async with sem:
                await loop.run_in_executor(None, _encode, n)
            r = str(n).encode()
        await nc.publish(msg.reply, r)

    async def handler(msg):
        asyncio.create_task(_process(msg))  # don't block the subscription

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

    payload = b"tiny" if a.task == "tiny" else f"embed:{a.batch}".encode()

    # dispatch latency: sequential round-trips
    lat = []
    for _ in range(a.ntiny):
        s = time.time()
        await nc.request("task", b"tiny", timeout=10)
        lat.append((time.time() - s) * 1e3)

    # throughput: bounded-concurrency gather over N requests
    sem = asyncio.Semaphore(a.concurrency)
    units = [0]
    rlat = []

    async def one():
        async with sem:
            s = time.time()
            r = await nc.request("task", payload, timeout=60)
            rlat.append((time.time() - s) * 1e3)
            units[0] += int(r.data.decode())

    t = time.time()
    await asyncio.gather(*[one() for _ in range(a.nreq)])
    dt = time.time() - t
    thr_req = a.nreq / dt
    thr_docs = units[0] / dt if a.task == "embed" else None

    for w in workers:
        w.terminate()
    await nc.close()
    srv.terminate()
    res = {
        "framework": "nats-bursting", "task": a.task, "workers": a.workers,
        "concurrency": a.concurrency, "setup_s": round(setup, 2),
        "dispatch_p50_ms": round(_pctl(lat, 50), 2),
        "dispatch_p99_ms": round(_pctl(lat, 99), 2),
        "throughput_req_s": round(thr_req, 1),
        "throughput_docs_s": round(thr_docs, 1) if thr_docs else None,
        "loaded_req_p50_ms": round(_pctl(rlat, 50), 1),
        "loaded_req_p99_ms": round(_pctl(rlat, 99), 1),
    }
    json.dump(res, open(a.out, "w"), indent=2)
    print(f"[bench] nats {a.task} W={a.workers} conc={a.concurrency}: "
          f"disp p50={res['dispatch_p50_ms']}ms | thr={res['throughput_req_s']} req/s"
          + (f" ({res['throughput_docs_s']} docs/s)" if thr_docs else "")
          + f" | loaded p50={res['loaded_req_p50_ms']}ms p99={res['loaded_req_p99_ms']}ms",
          flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["driver", "worker"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--task", default="embed", choices=["tiny", "embed"])
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--ntiny", type=int, default=40)
    ap.add_argument("--nreq", type=int, default=400)
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
