"""INFOCOM E1–E8 measurement harness for nats-bursting — core primitives.

Runs against a live NATS endpoint (core or JetStream) over any path
(LAN / Tailscale / duckdns:4222). Pairs with ``responder.py`` (far side) and is
driven by ``run.py``. Reuses the same nats-py the client uses (>=2.6).

Nothing here fabricates results: every function performs real requests/publishes
against a real server and reports measured latencies/throughput.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np
import nats


@dataclass
class Cfg:
    url: str  # nats://host:port  (the PATH under test)
    transport: str = "core"  # "core" | "js-durable" | "js-nondurable"
    path: str = "lan"  # label only: "lan" | "tailscale" | "duckdns"
    subject: str = "infocom.echo"
    stream: str = "INFOCOM"
    msg_size: int = 256  # request payload bytes
    n: int = 2000  # number of requests/publishes
    concurrency: int = 1  # in-flight window for throughput
    timeout: float = 5.0
    creds: Optional[str] = None  # NATS .creds path (NATS_BURSTING_NATS_CREDS)


def pctile(xs: list[float], p: float) -> float:
    return float(np.percentile(xs, p)) if xs else float("nan")


def _summary(lat_ms: list[float]) -> dict[str, float]:
    return {
        "n_ok": len(lat_ms),
        "mean_ms": float(np.mean(lat_ms)) if lat_ms else float("nan"),
        "p50_ms": pctile(lat_ms, 50),
        "p95_ms": pctile(lat_ms, 95),
        "p99_ms": pctile(lat_ms, 99),
    }


def _payload(size: int) -> bytes:
    return os.urandom(max(0, size))


async def connect(cfg: Cfg):
    """Open a NATS (and, for js modes, JetStream) connection; ensure the stream."""
    kw: dict[str, Any] = {}
    if cfg.creds:
        kw["user_credentials"] = cfg.creds
    nc = await nats.connect(cfg.url, **kw)
    js = None
    if cfg.transport.startswith("js"):
        js = nc.jetstream()
        storage = "file" if cfg.transport == "js-durable" else "memory"
        try:  # idempotent
            await js.add_stream(
                name=cfg.stream,
                subjects=[cfg.subject, cfg.subject + ".>"],
                storage=storage,
            )
        except Exception:
            pass
    return nc, js


async def measure_rtt(cfg: Cfg) -> dict[str, Any]:
    """Serial request→reply RTT against the echo responder (E1/E2 latency)."""
    nc, _ = await connect(cfg)
    pl = _payload(cfg.msg_size)
    for _ in range(max(1, min(50, cfg.n // 10))):  # warmup
        try:
            await nc.request(cfg.subject, pl, timeout=cfg.timeout)
        except Exception:
            pass
    lat: list[float] = []
    t0 = time.perf_counter()
    for _ in range(cfg.n):
        s = time.perf_counter()
        try:
            await nc.request(cfg.subject, pl, timeout=cfg.timeout)
            lat.append((time.perf_counter() - s) * 1e3)
        except Exception:
            pass
    wall = time.perf_counter() - t0
    await nc.drain()
    out = _summary(lat)
    out.update(sent=cfg.n, serial_rate_msgs_s=(len(lat) / wall if wall else 0.0))
    return out


async def measure_throughput(cfg: Cfg) -> dict[str, Any]:
    """Closed-loop throughput with a `concurrency` in-flight window (E1/E5)."""
    nc, _ = await connect(cfg)
    pl = _payload(cfg.msg_size)
    sem = asyncio.Semaphore(cfg.concurrency)
    lat: list[float] = []

    async def one() -> None:
        async with sem:
            s = time.perf_counter()
            try:
                await nc.request(cfg.subject, pl, timeout=cfg.timeout)
                lat.append((time.perf_counter() - s) * 1e3)
            except Exception:
                pass

    t0 = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(cfg.n)))
    wall = time.perf_counter() - t0
    await nc.drain()
    out = _summary(lat)
    out.update(
        sent=cfg.n,
        concurrency=cfg.concurrency,
        wall_s=wall,
        throughput_msgs_s=(len(lat) / wall if wall else 0.0),
    )
    return out


async def measure_js_publish(cfg: Cfg) -> dict[str, Any]:
    """JetStream publish→ack latency (E3 durability cost; storage set by transport)."""
    nc, js = await connect(cfg)
    assert js is not None, "measure_js_publish requires a js-* transport"
    pl = _payload(cfg.msg_size)
    lat: list[float] = []
    for _ in range(cfg.n):
        s = time.perf_counter()
        try:
            await js.publish(cfg.subject, pl)  # awaits the persistence ack
            lat.append((time.perf_counter() - s) * 1e3)
        except Exception:
            pass
    await nc.drain()
    out = _summary(lat)
    out.update(
        sent=cfg.n, storage=("file" if cfg.transport == "js-durable" else "memory")
    )
    return out


def meta() -> dict[str, Any]:
    def _git() -> str:
        try:
            return subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        except Exception:
            return "unknown"

    return {"host": socket.gethostname(), "git": _git(), "ts_unix": time.time()}


def write_results(
    path: str, experiment: str, cfg: Cfg, result: Any, extra: Optional[dict] = None
) -> None:
    rec: dict[str, Any] = {
        "experiment": experiment,
        "cfg": asdict(cfg),
        "meta": meta(),
        "result": result,
    }
    if extra:
        rec["extra"] = extra
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(rec, f, indent=2, default=str)
