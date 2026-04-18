"""Default module entry point for a Worker pod.

Most projects will ship their own `worker_entry.py`, but this one is
available out-of-the-box for smoke testing and for pools whose task
handlers live in a package imported via ``NATS_WORKER_HANDLERS``.

Environment:
    NATS_WORKER_HANDLERS    dotted path to a ``handlers`` dict
                            (default: none → echo worker)
"""

from __future__ import annotations

import importlib
import os

from .worker import run_worker


def _echo(task: dict) -> dict:
    return {"status": "echo", "received": task}


def _load_handlers():
    path = os.environ.get("NATS_WORKER_HANDLERS", "")
    if not path:
        return {"echo": _echo}
    mod_name, attr = path.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)


if __name__ == "__main__":
    run_worker(_load_handlers())
