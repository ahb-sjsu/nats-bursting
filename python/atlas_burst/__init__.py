"""Atlas-side Python client for the atlas-burst controller.

Publishes JobDescriptors to a NATS bus (typically exposed via Tailscale
Funnel) and reads back status events. Also ships an IPython cell magic
that lets you burst a Jupyter notebook cell to Nautilus when the local
GPU is busy.

Example
-------

    from atlas_burst import Client, JobDescriptor, Resources

    client = Client(nats_url="tls://atlas-xxxx.ts.net:443")
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

    %load_ext atlas_burst.magic
    %%burst --gpu 1 --memory 16Gi
    import torch
    torch.randn(1024, 1024).cuda()
"""

from __future__ import annotations

from atlas_burst.client import Client, SubmitResult
from atlas_burst.descriptor import JobDescriptor, Resources
from atlas_burst.probe import gpu_is_busy, probe_local_gpu

__all__ = [
    "Client",
    "JobDescriptor",
    "Resources",
    "SubmitResult",
    "gpu_is_busy",
    "probe_local_gpu",
]

__version__ = "0.1.0"
