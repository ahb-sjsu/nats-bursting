"""``%%burst`` IPython cell magic.

Packages the cell source into a Python-script ``JobDescriptor``,
submits it via an ``nats_bursting.Client``, and prints the resulting
Kubernetes Job name. Full log streaming is a follow-up — for now
users get the Job name and run ``kubectl logs -f job/<name>``
themselves.

Design
------
The magic defers choosing a NATS URL / credentials to environment
variables (``NATS_BURSTING_NATS_URL`` and ``NATS_BURSTING_NATS_CREDS``)
so a user's notebook stays portable across machines.

Argument parsing uses IPython's ``magic_arguments`` so ``%%burst?``
shows a proper help string.

Usage
-----

::

    %load_ext nats_bursting.magic

    %%burst --gpu 1 --memory 16Gi --image python:3.12-slim
    import torch
    print(torch.cuda.is_available())

Flags
-----
--when-busy  (default) Run locally if the local GPU has headroom; burst otherwise.
--always     Burst unconditionally.
--never      Run locally unconditionally (useful for debugging the magic).
--gpu N      Request N GPUs in the burst pod.
--cpu X      Kubernetes CPU request (e.g. "2", "500m").
--memory X   Kubernetes memory request (e.g. "16Gi").
--image IMG  Container image; default is ``python:3.12-slim``.
--timeout S  Seconds to wait for the submit-ack. Default 60.
--dry-run    Print the JobDescriptor JSON but do not submit.
"""

from __future__ import annotations

import os
import uuid

from nats_bursting.client import Client
from nats_bursting.descriptor import JobDescriptor, Resources
from nats_bursting.probe import gpu_is_busy

_HAS_IPYTHON = False
try:
    from IPython.core.magic import Magics, cell_magic, magics_class
    from IPython.core.magic_arguments import (
        argument,
        magic_arguments,
        parse_argstring,
    )

    _HAS_IPYTHON = True
except ImportError:  # pragma: no cover — optional dep
    # Stub fallbacks so non-Jupyter imports of nats_bursting still work.
    def cell_magic(func):  # type: ignore[misc]
        return func

    def magics_class(cls):  # type: ignore[misc]
        return cls

    class Magics:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            pass

    def magic_arguments():  # type: ignore[misc]
        def deco(f):
            return f

        return deco

    def argument(*_a, **_kw):  # type: ignore[misc]
        def deco(f):
            return f

        return deco

    def parse_argstring(*_a, **_kw):  # type: ignore[misc]
        raise RuntimeError("IPython is not available")


DEFAULT_IMAGE = "python:3.12-slim"


@magics_class
class BurstMagic(Magics):  # type: ignore[misc]
    """Container for ``%%burst``. Registered by ``load_ipython_extension``."""

    def __init__(self, shell=None, client: Client | None = None):
        super().__init__(shell)
        self._client_override = client

    def _client(self) -> Client:
        if self._client_override is not None:
            return self._client_override
        url = os.environ.get("NATS_BURSTING_NATS_URL", "nats://localhost:4222")
        creds = os.environ.get("NATS_BURSTING_NATS_CREDS") or None
        return Client(nats_url=url, nats_creds=creds)

    @magic_arguments()
    @argument(
        "--when-busy",
        action="store_true",
        default=True,
        help="Burst only when local GPU is busy (default).",
    )
    @argument("--always", action="store_true", help="Burst unconditionally.")
    @argument("--never", action="store_true", help="Run locally unconditionally.")
    @argument("--gpu", type=int, default=0, help="GPU count for the burst pod.")
    @argument("--cpu", type=str, default="", help="CPU request (e.g. '2').")
    @argument("--memory", type=str, default="", help="Memory request (e.g. '16Gi').")
    @argument("--image", type=str, default=DEFAULT_IMAGE, help="Container image.")
    @argument("--timeout", type=float, default=60.0, help="Submit-ack timeout (s).")
    @argument("--dry-run", action="store_true", help="Print descriptor, don't submit.")
    @cell_magic
    def burst(self, line: str, cell: str):
        """Run the cell via nats-bursting on Nautilus."""
        if not _HAS_IPYTHON:  # pragma: no cover
            raise RuntimeError("nats_bursting.magic requires IPython")

        args = parse_argstring(self.burst, line)

        if args.never:
            return _run_locally(cell, self.shell)

        # --when-busy (default): only burst if GPU busy
        if not args.always and not gpu_is_busy():
            return _run_locally(cell, self.shell)

        desc = _build_descriptor(cell, args)

        if args.dry_run:
            print(desc.to_json().decode("utf-8"))
            return None

        client = self._client()
        result = client.submit_and_wait(desc, timeout=args.timeout)
        if result.accepted:
            print(
                f"[burst] submitted job_id={result.job_id} "
                f"k8s_job={result.k8s_job_name}"
            )
            print(f"[burst] follow with: kubectl logs -f job/{result.k8s_job_name}")
        else:
            reason = result.status.reason if result.status else "no status"
            print(f"[burst] submission FAILED: {reason}")
        return result


def _run_locally(cell: str, shell) -> None:
    """Execute the cell in the current IPython shell (no bursting)."""
    if shell is None:  # pragma: no cover — defensive
        exec(cell, {})  # noqa: S102
        return
    shell.run_cell(cell)


def _build_descriptor(cell: str, args) -> JobDescriptor:
    name = f"burst-{uuid.uuid4().hex[:12]}"
    env = {"NATS_BURSTING_CELL": cell}
    # Run the cell via: python -c "$NATS_BURSTING_CELL"
    # Env limit is 1 MiB, which fits any realistic notebook cell.
    command = ["sh", "-c", 'python -c "$NATS_BURSTING_CELL"']
    return JobDescriptor(
        name=name,
        image=args.image,
        command=command,
        env=env,
        resources=Resources(
            cpu=args.cpu,
            memory=args.memory,
            gpu=int(args.gpu or 0),
        ),
        labels={"nats-bursting.io/origin": "magic"},
    )


def load_ipython_extension(ipython):  # pragma: no cover — integration path
    """IPython entry point: ``%load_ext nats_bursting.magic`` calls this."""
    ipython.register_magics(BurstMagic)
