"""Persistent worker pools over NATS.

Where :class:`~nats_bursting.descriptor.JobDescriptor` submits **ephemeral
bursts** — one-shot Kubernetes Jobs that appear, run, and disappear — a
:class:`Pool` describes a **persistent worker deployment**: N always-on
pods subscribed to a NATS JetStream work-queue, pulling tasks as fast as
they can handle them.

Two shapes, one bus:

    ephemeral burst         : fire-and-forget Job     (cheap ramp-up, cheap teardown)
    persistent pool (here)  : always-on Deployment    (no cold-start per task)

Use a Pool when:
 - You have many small, frequent tasks (<= a few minutes each).
 - Per-task container cold-start would dominate.
 - You want the worker to stay warm with pre-downloaded models / caches.

The Atlas side publishes tasks with
:func:`publish_task` / :class:`TaskDispatcher`; pod-side code runs inside
:class:`Worker`. Both use the same JetStream stream so messages are
persisted, load-balanced across pods in the same durable consumer group,
and redelivered on ack timeout.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any


# ─── Data classes ────────────────────────────────────────────────────

@dataclass
class PoolDescriptor:
    """High-level description of a persistent worker pool.

    Rendered into a Kubernetes Deployment manifest by
    :func:`pool_manifest`. The container runs an image that starts a
    :class:`Worker` loop (usually via a project-specific entry script).
    """

    #: Deployment name (k8s DNS-1123 label)
    name: str
    #: Kubernetes namespace to deploy into
    namespace: str
    #: Container image (must have python + nats-py, or install at startup)
    image: str = "gcr.io/kaggle-images/python:latest"
    #: Replica count (for NRP: keep each pod lightweight; no cap from quota
    #: unless you request A100s)
    replicas: int = 8
    #: Per-pod resources. On NRP, stay at cpu=1/memory=2Gi to remain in
    #: swarm-mode (any replica count allowed). Bigger pods trigger the
    #: "heavy mode" cap of 4 pods.
    cpu: str = "1"
    memory: str = "2Gi"
    gpu: int = 0
    #: Durable consumer group — identifies the set of workers that
    #: cooperate on a single JetStream work-queue.
    consumer_group: str = "workers"
    #: JetStream stream name (auto-created by the worker if missing).
    stream: str = "TASKS"
    #: Subject glob that the workers pull from.
    subjects: list[str] = field(default_factory=lambda: ["tasks.>"])
    #: Commands to run before the worker entry, e.g. ``["pip install foo"]``.
    pre_install: list[str] = field(default_factory=list)
    #: The entrypoint. Typically fetches project code and execs a worker.
    entry: list[str] = field(default_factory=lambda: [
        "python3", "-u", "-m", "nats_bursting.worker_entry"
    ])
    #: Env vars passed to the pod. ``NATS_URL`` defaults to the in-cluster
    #: leaf service at ``nats://atlas-nats:4222``.
    env: dict[str, str] = field(default_factory=dict)
    #: Secret names to mount as env vars. Map ``{env_var: (secret, key)}``.
    env_from_secrets: dict[str, tuple[str, str]] = field(default_factory=dict)


# ─── Manifest generation ─────────────────────────────────────────────

def pool_manifest(desc: PoolDescriptor) -> str:
    """Render a Deployment manifest (YAML string) from a PoolDescriptor."""
    env_lines: list[str] = []
    for k, v in desc.env.items():
        env_lines.append(f"        - name: {k}\n          value: {json.dumps(v)}")
    for k, (secret, key) in desc.env_from_secrets.items():
        env_lines.append(
            f"        - name: {k}\n"
            f"          valueFrom:\n"
            f"            secretKeyRef:\n"
            f"              name: {secret}\n"
            f"              key: {key}"
        )
    # Inject required env (NATS_URL + consumer_group + stream)
    for k, v in (
        ("NATS_URL", desc.env.get("NATS_URL", "nats://atlas-nats:4222")),
        ("NATS_CONSUMER_GROUP", desc.consumer_group),
        ("NATS_STREAM", desc.stream),
        ("NATS_SUBJECTS", ",".join(desc.subjects)),
    ):
        if k not in desc.env and k not in desc.env_from_secrets:
            env_lines.append(f"        - name: {k}\n          value: {json.dumps(v)}")
    env_block = "\n".join(env_lines) or "        []"

    resources = {
        "requests": {"cpu": desc.cpu, "memory": desc.memory},
        "limits":   {"cpu": desc.cpu, "memory": desc.memory},
    }
    if desc.gpu:
        resources["requests"]["nvidia.com/gpu"] = str(desc.gpu)
        resources["limits"]["nvidia.com/gpu"] = str(desc.gpu)

    pre_install_sh = " && ".join(desc.pre_install) if desc.pre_install else "true"
    # The worker *command* is split: we install prereqs in bash, then exec
    # the entry. This keeps image re-use high — same base image, different
    # installed deps per project.
    bash_script = textwrap.dedent(f"""
        set -e
        pip install --quiet nats-py
        {pre_install_sh}
        exec {' '.join(desc.entry)}
    """).strip()

    return textwrap.dedent(f"""\
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: {desc.name}
      namespace: {desc.namespace}
      labels:
        app: {desc.name}
        nats-bursting.role: pool-worker
    spec:
      replicas: {desc.replicas}
      strategy:
        type: RollingUpdate
        rollingUpdate:
          maxUnavailable: 2
          maxSurge: 2
      selector:
        matchLabels:
          app: {desc.name}
      template:
        metadata:
          labels:
            app: {desc.name}
            nats-bursting.role: pool-worker
        spec:
          restartPolicy: Always
          containers:
          - name: worker
            image: {desc.image}
            resources: {json.dumps(resources)}
            env:
    {env_block}
            command: ["/bin/bash", "-c"]
            args:
            - |
              {bash_script.replace(chr(10), chr(10)+'              ')}
    """)


# ─── Atlas-side dispatch ─────────────────────────────────────────────

async def publish_task(nc, subject: str, payload: dict,
                       stream: str = "TASKS") -> int:
    """Publish one task onto the JetStream work queue.

    ``nc`` is an open :class:`nats.aio.client.Client`.
    Returns the stream sequence number on success.
    """
    from nats.js.api import StreamConfig, RetentionPolicy
    js = nc.jetstream()
    try:
        await js.stream_info(stream)
    except Exception:
        await js.add_stream(StreamConfig(
            name=stream, subjects=[subject.split(".", 1)[0] + ".>"],
            retention=RetentionPolicy.WORK_QUEUE, max_msgs=100_000,
        ))
    ack = await js.publish(subject, json.dumps(payload).encode())
    return ack.seq


class TaskDispatcher:
    """Tiny wrapper: open NATS, publish many, optionally collect results.

    ::

        async with TaskDispatcher(nats_url) as td:
            ids = await td.submit_many("tasks.solve", [{...}, {...}])
            results = await td.collect(ids, timeout=120)
    """

    def __init__(self, nats_url: str, stream: str = "TASKS",
                 result_prefix: str = "results."):
        self.nats_url = nats_url
        self.stream = stream
        self.result_prefix = result_prefix
        self._nc = None
        self._result_sub = None

    async def __aenter__(self):
        import nats
        self._nc = await nats.connect(self.nats_url)
        self._result_sub = await self._nc.subscribe(self.result_prefix + ">")
        return self

    async def __aexit__(self, *exc):
        if self._nc is not None:
            await self._nc.drain()

    async def submit_many(self, subject: str, payloads: list[dict]) -> list[str]:
        import uuid
        ids = []
        for p in payloads:
            tid = p.setdefault("id", uuid.uuid4().hex[:12])
            await publish_task(self._nc, subject, p, stream=self.stream)
            ids.append(tid)
        return ids

    async def collect(self, ids: list[str], timeout: float = 60) -> dict:
        """Collect results keyed by task id, waiting up to ``timeout``
        seconds per remaining task. Missing results return ``None``."""
        import asyncio
        pending = set(ids)
        out: dict[str, Any] = {}
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while pending and loop.time() < deadline:
            try:
                msg = await asyncio.wait_for(self._result_sub.next_msg(),
                                             timeout=max(1, deadline - loop.time()))
            except asyncio.TimeoutError:
                break
            try:
                p = json.loads(msg.data.decode())
            except json.JSONDecodeError:
                continue
            tid = p.get("task_id") or p.get("id")
            if tid in pending:
                out[tid] = p
                pending.remove(tid)
        for tid in pending:
            out[tid] = None
        return out
