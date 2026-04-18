"""Atlas-side Python client for the nats-bursting controller.

Two shapes, one NATS bus:

1. **Ephemeral bursts** — :class:`JobDescriptor` + :class:`Client`: submit
   a one-shot Kubernetes Job to a shared cluster, get results back over
   NATS, pod disappears.

2. **Persistent pools** — :class:`PoolDescriptor` + :class:`Worker`: run
   N always-on pods subscribed to a JetStream work queue, pulling tasks
   as fast as they can handle them. No cold-start per task.

Ephemeral example::

    from nats_bursting import Client, JobDescriptor, Resources
    client = Client(nats_url="nats://localhost:4222")
    client.submit_and_wait(JobDescriptor(
        name="hello", image="python:3.12-slim",
        command=["python", "-c", "print('hello from nautilus')"],
        resources=Resources(cpu="1", memory="1Gi"),
    ), timeout=300)

Pool example (see :mod:`nats_bursting.pool` and :mod:`nats_bursting.worker`
for full docs)::

    from nats_bursting import PoolDescriptor, pool_manifest
    yaml = pool_manifest(PoolDescriptor(
        name="my-workers", namespace="my-ns", replicas=8,
        pre_install=["pip install --quiet openai"],
        entry=["python3", "-u", "-m", "my_project.worker_main"],
    ))
    # kubectl apply -f <(echo "$yaml")

IPython magic (ephemeral only)::

    %load_ext nats_bursting.magic
    %%burst --gpu 1 --memory 16Gi
    import torch
    torch.randn(1024, 1024).cuda()
"""

from __future__ import annotations

from nats_bursting.client import Client, SubmitResult
from nats_bursting.descriptor import JobDescriptor, Resources
from nats_bursting.pool import PoolDescriptor, TaskDispatcher, pool_manifest, publish_task
from nats_bursting.probe import gpu_is_busy, probe_local_gpu
from nats_bursting.worker import Worker, run_worker

__all__ = [
    "Client",
    "JobDescriptor",
    "PoolDescriptor",
    "Resources",
    "SubmitResult",
    "TaskDispatcher",
    "Worker",
    "gpu_is_busy",
    "pool_manifest",
    "probe_local_gpu",
    "publish_task",
    "run_worker",
]

__version__ = "0.1.0"
