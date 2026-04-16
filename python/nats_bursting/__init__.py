"""Atlas-side Python client for the nats-bursting controller.

Publishes JobDescriptors to the local Atlas NATS bus (which extends
into NRP via a leaf-node bridge) and reads back status events.
Also ships an IPython cell magic that lets you burst a Jupyter
notebook cell to NRP when the local GPU is busy.

Example
-------

    from nats_bursting import Client, JobDescriptor, Resources

    client = Client(nats_url="nats://localhost:4222")
    job_name = client.submit_and_wait(
        JobDescriptor(
            name="hello",
            image="python:3.12-slim",
            command=["python", "-c", "print('hello from nautilus')"],
            resources=Resources(cpu="1", memory="1Gi"),
        ),
        timeout=300,
    )
    print(job_name)

IPython magic::

    %load_ext nats_bursting.magic
    %%burst --gpu 1 --memory 16Gi
    import torch
    torch.randn(1024, 1024).cuda()
"""

from __future__ import annotations

from nats_bursting.client import Client, SubmitResult
from nats_bursting.descriptor import JobDescriptor, Resources
from nats_bursting.probe import gpu_is_busy, probe_local_gpu

__all__ = [
    "Client",
    "JobDescriptor",
    "Resources",
    "SubmitResult",
    "gpu_is_busy",
    "probe_local_gpu",
]

__version__ = "0.1.0"
