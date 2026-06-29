#!/usr/bin/env python3
"""nats-bursting GPU burst worker for E8 guest jobs.

Does real GPU matmul for HOLD_SEC (no sleep -> ban-safe), publishes a result to
``<NATS_RESULT_PREFIX><JOB_ID>`` on NATS, and exits 0. All parameters come from env
(the controller renders ``JobDescriptor.env`` into the pod):

  NATS_URL           in-cluster leaf, default nats://atlas-nats:4222
  NATS_RESULT_PREFIX default "results."
  JOB_ID             result subject suffix (set by the submitter/driver)
  HOLD_SEC           compute duration, default 20
  MATMUL_SIZE        square matmul dimension, default 4096
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time


def run_matmul(hold: float, size: int) -> tuple[str, int]:
    import torch

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    x = torch.randn(size, size, device=dev)
    t_end = time.time() + hold
    iters = 0
    while time.time() < t_end:
        x = (x @ x).remainder_(7.0).add_(1.0)
        iters += 1
    if dev == "cuda":
        torch.cuda.synchronize()
    return dev, iters


async def _publish(url: str, subject: str, payload: dict) -> None:
    import nats

    nc = await nats.connect(url, connect_timeout=10, max_reconnect_attempts=5)
    await nc.publish(subject, json.dumps(payload).encode())
    await nc.flush()
    await nc.drain()


def main() -> None:
    url = os.environ.get("NATS_URL", "nats://atlas-nats:4222")
    prefix = os.environ.get("NATS_RESULT_PREFIX", "results.")
    job_id = (
        os.environ.get("JOB_ID") or os.environ.get("HOSTNAME") or socket.gethostname()
    )
    hold = float(os.environ.get("HOLD_SEC", "20"))
    size = int(os.environ.get("MATMUL_SIZE", "4096"))

    t0 = time.time()
    dev, iters = run_matmul(hold, size)
    payload = {
        "job_id": job_id,
        "status": "done",
        "device": dev,
        "elapsed_s": round(time.time() - t0, 3),
        "iters": iters,
    }
    asyncio.run(_publish(url, prefix + job_id, payload))
    print("published", prefix + job_id, json.dumps(payload), flush=True)


if __name__ == "__main__":
    main()
