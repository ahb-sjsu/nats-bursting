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
    """Render a Deployment manifest (YAML string) from a PoolDescriptor.

    Built line-by-line (no textwrap.dedent) so indentation is predictable
    and multi-line env entries don't collapse under common-prefix stripping.
    """
    # env entries
    env_entries: list[list[str]] = []
    seen: set[str] = set()
    for k, v in desc.env.items():
        env_entries.append([f"- name: {k}", f"  value: {json.dumps(v)}"])
        seen.add(k)
    for k, (secret, key) in desc.env_from_secrets.items():
        env_entries.append([
            f"- name: {k}",
            "  valueFrom:",
            "    secretKeyRef:",
            f"      name: {secret}",
            f"      key: {key}",
        ])
        seen.add(k)
    # Inject required env unless the caller set them
    for k, v in (
        ("NATS_URL", desc.env.get("NATS_URL", "nats://atlas-nats:4222")),
        ("NATS_CONSUMER_GROUP", desc.consumer_group),
        ("NATS_STREAM", desc.stream),
        ("NATS_SUBJECTS", ",".join(desc.subjects)),
    ):
        if k not in seen:
            env_entries.append([f"- name: {k}", f"  value: {json.dumps(v)}"])

    # Each env line sits at 8-space indent (under `env:` which is at 8).
    env_block_lines: list[str] = []
    for entry in env_entries:
        for ln in entry:
            env_block_lines.append("        " + ln)

    resources = {
        "requests": {"cpu": desc.cpu, "memory": desc.memory},
        "limits":   {"cpu": desc.cpu, "memory": desc.memory},
    }
    if desc.gpu:
        resources["requests"]["nvidia.com/gpu"] = str(desc.gpu)
        resources["limits"]["nvidia.com/gpu"] = str(desc.gpu)

    pre_install_sh = " && ".join(desc.pre_install) if desc.pre_install else "true"
    bash_lines = [
        "set -e",
        "pip install --quiet nats-py",
        pre_install_sh,
        f"exec {' '.join(desc.entry)}",
    ]
    # 14-space indent under `args: - |`
    bash_block_lines = ["              " + ln for ln in bash_lines]

    out: list[str] = [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        f"  name: {desc.name}",
        f"  namespace: {desc.namespace}",
        "  labels:",
        f"    app: {desc.name}",
        "    nats-bursting.role: pool-worker",
        "spec:",
        f"  replicas: {desc.replicas}",
        "  strategy:",
        "    type: RollingUpdate",
        "    rollingUpdate:",
        "      maxUnavailable: 2",
        "      maxSurge: 2",
        "  selector:",
        "    matchLabels:",
        f"      app: {desc.name}",
        "  template:",
        "    metadata:",
        "      labels:",
        f"        app: {desc.name}",
        "        nats-bursting.role: pool-worker",
        "    spec:",
        "      restartPolicy: Always",
        "      containers:",
        "      - name: worker",
        f"        image: {desc.image}",
        f"        resources: {json.dumps(resources)}",
        "        env:",
        *env_block_lines,
        '        command: ["/bin/bash", "-c"]',
        "        args:",
        "        - |",
        *bash_block_lines,
    ]
    return "\n".join(out) + "\n"


# ─── Atlas-side dispatch ─────────────────────────────────────────────

async def publish_task(nc, subject: str, payload: dict,
                       stream: str = "TASKS") -> int:
    """Publish one task onto the JetStream work queue.

    ``nc`` is an open :class:`nats.aio.client.Client`.
    Returns the stream sequence number on success.
    """
    from nats.js.api import RetentionPolicy, StreamConfig
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

    ``durable=True`` (default) routes through JetStream — requires the
    stream to exist on the NATS server you connect to AND be reachable
    from the worker's NATS server (i.e. shared JS context). Best for
    same-server or JS-domain-federated setups.

    ``durable=False`` uses core NATS publish — crosses leaf-node
    boundaries transparently, works when dispatcher and workers live
    on different NATS servers without JS federation.

    ::

        async with TaskDispatcher(nats_url, durable=False) as td:
            ids = await td.submit_many("tasks.solve", [{...}, {...}])
            results = await td.collect(ids, timeout=120)
    """

    def __init__(self, nats_url: str, stream: str = "TASKS",
                 result_prefix: str = "results.",
                 durable: bool = True):
        self.nats_url = nats_url
        self.stream = stream
        self.result_prefix = result_prefix
        self.durable = durable
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
            if self.durable:
                await publish_task(self._nc, subject, p, stream=self.stream)
            else:
                await self._nc.publish(subject, json.dumps(p).encode())
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
