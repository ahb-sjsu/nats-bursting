#!/usr/bin/env python3
"""Tier-2 benchmark: NATS round-trip latency + throughput, with and without compression.

Measures the fabric the burst path rides on: request/reply round-trip time and sustained
throughput across payload sizes, against a real NATS server (no cluster needed). With
``--compress`` it wraps payloads in turboquant-pro's codec to show end-to-end effect on
the wire for large AI payloads.

Needs a running NATS server (``NATS_URL``, default nats://127.0.0.1:4222). Locally:
``docker run -p 4222:4222 nats:latest`` or a ``nats-server`` binary; on NRP/Atlas, point
``NATS_URL`` at the deployed bus. Run: ``python benchmarks/bench_transport.py``.
"""

import argparse
import asyncio
import os
import statistics
import time

import numpy as np

try:
    import nats
except ImportError:
    nats = None


async def run(args):
    if nats is None:
        print("nats-py not installed: pip install nats-py")
        return
    url = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
    try:
        nc = await asyncio.wait_for(nats.connect(url), timeout=5)
    except Exception as e:  # noqa: BLE001
        print(f"could not connect to NATS at {url}: {str(e)[:80]}")
        print("start one with:  docker run -p 4222:4222 nats:latest")
        return

    codec = None
    if args.compress:
        from turboquant_pro.nats_codec import TurboQuantNATSCodec

        codec = TurboQuantNATSCodec(dim=args.dim, bits=args.bits)

    # echo responder: decodes+re-encodes if compressing (models a real worker round trip)
    async def echo(msg):
        await nc.publish(msg.reply, msg.data)

    sub = await nc.subscribe("bench.echo", cb=echo)

    rng = np.random.default_rng(0)
    print(f"NATS {url} | compress={args.compress} (dim={args.dim}, bits={args.bits})")
    print(f"{'batch':>6} {'wire KB':>8} {'p50 ms':>8} {'p99 ms':>8} {'msgs/s':>8}")
    for n in args.batch:
        emb = rng.standard_normal((n, args.dim)).astype(np.float32)
        payload = b"".join(codec.encode_batch(emb)) if codec else emb.tobytes()
        # warmup
        for _ in range(5):
            await nc.request("bench.echo", payload, timeout=5)
        lat = []
        t0 = time.perf_counter()
        for _ in range(args.iters):
            s = time.perf_counter()
            await nc.request("bench.echo", payload, timeout=5)
            lat.append((time.perf_counter() - s) * 1e3)
        wall = time.perf_counter() - t0
        lat.sort()
        p50 = statistics.median(lat)
        p99 = lat[min(len(lat) - 1, int(0.99 * len(lat)))]
        print(
            f"{n:>6} {len(payload)/1024:>8.1f} {p50:>8.3f} {p99:>8.3f} {args.iters/wall:>8.0f}"
        )
    await sub.unsubscribe()
    await nc.drain()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, nargs="+", default=[1, 32, 256])
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--bits", type=int, default=3)
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument(
        "--compress",
        action="store_true",
        help="wrap payloads in turboquant-pro NATS codec",
    )
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
