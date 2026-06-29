"""Far-side responder for the INFOCOM harness.

Run this on the cluster you burst *to*; the driver (``run.py``) runs on the home
node. It echo-replies to every request on ``--subject`` (RTT/throughput), with an
optional emulated per-request work delay.

    python responder.py --url nats://0.0.0.0:4222 --subject infocom.echo
"""

from __future__ import annotations

import argparse
import asyncio
import os

import nats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url", default=os.environ.get("NATS_URL", "nats://localhost:4222")
    )
    ap.add_argument("--subject", default="infocom.echo")
    ap.add_argument("--creds", default=os.environ.get("NATS_BURSTING_NATS_CREDS"))
    ap.add_argument(
        "--work-ms",
        type=float,
        default=0.0,
        help="emulated per-request work before replying",
    )
    a = ap.parse_args()

    kw = {"user_credentials": a.creds} if a.creds else {}
    nc = await nats.connect(a.url, **kw)

    async def cb(msg) -> None:
        if a.work_ms:
            await asyncio.sleep(a.work_ms / 1000.0)
        if msg.reply:
            await nc.publish(msg.reply, msg.data)

    await nc.subscribe(a.subject, cb=cb)
    print(
        f"[responder] up on {a.url} subject={a.subject} work_ms={a.work_ms}", flush=True
    )
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await nc.drain()


if __name__ == "__main__":
    asyncio.run(main())
