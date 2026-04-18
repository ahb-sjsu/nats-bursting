"""Pod-side worker runtime for persistent task pools.

Import this in your project's worker entrypoint, register handlers, then
call :func:`run_worker` to block forever processing tasks.

Minimal example::

    from nats_bursting.worker import Worker, run_worker

    def handle_solve(task: dict) -> dict:
        return {"status": "solved", "n": task["n"] ** 2}

    run_worker(handlers={"solve": handle_solve})

The worker:
 - connects to ``NATS_URL`` (env),
 - creates (or reuses) a JetStream work-queue stream,
 - opens a durable pull consumer named after ``NATS_CONSUMER_GROUP`` so
   multiple pod replicas share the same queue,
 - fetches one task at a time, dispatches by ``task["type"]``,
 - publishes the handler's return value to ``results.<task_id>``,
 - acks on success, naks on exception.

It never sleeps-to-idle: if the queue is empty it blocks inside
``sub.fetch()`` until a task arrives, which satisfies NRP's
"no sleeping Jobs" policy.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import time
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger("nats_bursting.worker")

TaskHandler = Callable[[dict], dict]


def _get(env_key: str, default: str = "") -> str:
    return os.environ.get(env_key, default)


@dataclass
class Worker:
    """Encapsulates one pod's task-loop configuration.

    ``durable=True`` (default) uses JetStream: work-queue retention,
    at-least-once delivery, ack/nak with configurable redelivery.
    Requires worker and dispatcher to share a JetStream context
    (same NATS server, or federated JS domains).

    ``durable=False`` uses **core NATS queue groups**: all workers
    subscribed to the same ``(subject, queue)`` share incoming
    messages round-robin. No persistence, no redelivery on worker
    crash — but it crosses leaf-node boundaries transparently, so
    it's the right choice when dispatcher and workers are on
    different NATS servers linked by leaf nodes without JS federation.
    """

    handlers: Mapping[str, TaskHandler]
    nats_url: str = field(
        default_factory=lambda: _get("NATS_URL", "nats://atlas-nats:4222")
    )
    stream: str = field(default_factory=lambda: _get("NATS_STREAM", "TASKS"))
    subjects: list[str] = field(
        default_factory=lambda: _get("NATS_SUBJECTS", "tasks.>").split(",")
    )
    consumer_group: str = field(
        default_factory=lambda: _get("NATS_CONSUMER_GROUP", "workers")
    )
    result_prefix: str = field(
        default_factory=lambda: _get("NATS_RESULT_PREFIX", "results.")
    )
    durable: bool = field(
        default_factory=lambda: _get("NATS_DURABLE", "1") not in ("0", "false", "False")
    )
    # Optional HTTP webhook — POST each result here in addition to publishing
    # on NATS. Useful when NATS leaf-node interest propagation is asymmetric
    # (tasks flow hub→spoke but results don't flow back). The webhook server
    # can re-publish on the hub's local NATS so subscribers see results
    # transparently.
    result_webhook_url: str = field(
        default_factory=lambda: _get("RESULT_WEBHOOK_URL", "")
    )
    ack_wait_s: int = 300
    fetch_timeout_s: int = 30

    async def _ensure_stream(self, js):
        from nats.js.api import RetentionPolicy, StreamConfig

        try:
            await js.stream_info(self.stream)
        except Exception:
            log.info(f"creating stream {self.stream}")
            await js.add_stream(
                StreamConfig(
                    name=self.stream,
                    subjects=self.subjects,
                    retention=RetentionPolicy.WORK_QUEUE,
                    max_msgs=100_000,
                    max_age=86400 * 7,
                )
            )

    async def _handle(self, nc, data: bytes, ack_callback=None) -> None:
        """Shared handler: used by both JS and core-NATS modes."""
        t0 = time.time()
        try:
            task = json.loads(data.decode())
        except Exception as e:
            log.warning(f"bad task payload: {e}")
            if ack_callback:
                await ack_callback(ok=False)
            return
        task_id = task.get("id", "anon")
        task_type = task.get("type") or task.get("task_type")
        handler = self.handlers.get(task_type)
        if handler is None:
            result = {"error": f"no handler for task type {task_type!r}"}
        else:
            try:
                maybe = handler(task)
                if asyncio.iscoroutine(maybe):
                    result = await maybe
                else:
                    result = maybe or {}
            except Exception as e:
                result = {
                    "error": str(e)[:500],
                    "traceback": traceback.format_exc()[:1000],
                }
        result["task_id"] = task_id
        result["task_type"] = task_type
        result["worker"] = os.environ.get("HOSTNAME", "anon")
        result["ts"] = datetime.utcnow().isoformat() + "Z"
        result["duration_s"] = round(time.time() - t0, 2)
        await nc.publish(
            self.result_prefix + str(task_id), json.dumps(result, default=str).encode()
        )
        # Optional: also POST to the HTTP webhook so results reach the
        # dispatch origin even when NATS leaf routing is asymmetric.
        if self.result_webhook_url:
            try:
                import urllib.request

                req = urllib.request.Request(
                    self.result_webhook_url,
                    data=json.dumps(result, default=str).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                # Short timeout — webhook is best-effort; NATS publish is
                # authoritative.
                await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
            except Exception as e:
                log.warning(f"[{task_id}] webhook POST failed: {e}")
        if ack_callback:
            await ack_callback(ok=True)
        log.info(f"[{task_id}] {task_type} done in {result['duration_s']}s")

    async def _run_jetstream(self, nc):
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

        js = nc.jetstream()
        await self._ensure_stream(js)
        durable_name = f"{self.consumer_group}-consumer"
        subject_filter = self.subjects[0] if len(self.subjects) == 1 else ">"
        sub = await js.pull_subscribe(
            subject=subject_filter,
            durable=durable_name,
            config=ConsumerConfig(
                ack_policy=AckPolicy.EXPLICIT,
                ack_wait=self.ack_wait_s,
                max_deliver=3,
                deliver_policy=DeliverPolicy.ALL,
            ),
        )
        log.info(
            f"worker ready (JetStream) group={self.consumer_group} "
            f"subjects={self.subjects} handlers={list(self.handlers)}"
        )
        stopping = {"flag": False}

        def _stop(*_):
            stopping["flag"] = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError):
                signal.signal(sig, _stop)
        while not stopping["flag"]:
            try:
                msgs = await sub.fetch(1, timeout=self.fetch_timeout_s)
            except TimeoutError:
                continue
            except Exception as e:
                log.warning(f"fetch error: {e}")
                await asyncio.sleep(2)
                continue
            for msg in msgs:
                # Bind msg per-iteration so the closure doesn't capture
                # the loop variable.
                async def _ack(ok, _msg=msg):
                    if ok:
                        await _msg.ack()
                    else:
                        await _msg.nak()

                await self._handle(nc, msg.data, _ack)

    async def _run_core(self, nc):
        """Core-NATS queue-group mode — no persistence, crosses leaf
        boundaries transparently."""
        done = asyncio.Event()

        def _stop(*_):
            done.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(ValueError):
                signal.signal(sig, _stop)

        async def _cb(msg):
            await self._handle(nc, msg.data)

        for subj in self.subjects:
            await nc.subscribe(subj, queue=self.consumer_group, cb=_cb)

        log.info(
            f"worker ready (core NATS queue) group={self.consumer_group} "
            f"subjects={self.subjects} handlers={list(self.handlers)}"
        )
        await done.wait()

    async def run(self) -> None:
        import nats

        log.info(f"connecting NATS: {self.nats_url} durable={self.durable}")
        nc = await nats.connect(
            self.nats_url, max_reconnect_attempts=-1, reconnect_time_wait=2
        )
        try:
            if self.durable:
                await self._run_jetstream(nc)
            else:
                await self._run_core(nc)
        finally:
            await nc.drain()
            log.info("worker exiting")


def run_worker(handlers: Mapping[str, TaskHandler], **kwargs) -> None:
    """Blocking entry point: construct a :class:`Worker` and run it.

    Handlers map ``task["type"]`` → callable. Callables may be sync or
    async; return value (a dict) is published on ``results.{task_id}``.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = Worker(handlers=handlers, **kwargs)
    asyncio.run(worker.run())
