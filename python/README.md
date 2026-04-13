# atlas-burst (Python client)

Atlas-side Python client + IPython cell magic for the
[atlas-burst](https://github.com/ahb-sjsu/atlas-burst) controller.

The Go controller (in the parent directory) listens on a NATS bus and
dispatches Kubernetes Jobs to a remote cluster (e.g. NRP Nautilus).
This package is the **submitter**: it lets a Python script — or a
Jupyter notebook cell via the `%%burst` magic — publish job
descriptions to the controller and wait for an acknowledgement.

## Install

```bash
pip install -e atlas-burst/python                        # local checkout
pip install 'git+https://github.com/ahb-sjsu/atlas-burst.git#subdirectory=python'  # from GitHub
```

Optional extras: `[ipython]` for the cell magic, `[dev]` for tests + lint.

## Two ways to use it

### 1. Library API

```python
from atlas_burst import Client, JobDescriptor, Resources

client = Client(nats_url="tls://atlas-xxxx.ts.net:443")
result = client.submit_and_wait(
    JobDescriptor(
        name="hello",
        image="python:3.12-slim",
        command=["python", "-c", "print('hi from nautilus')"],
        resources=Resources(cpu="1", memory="1Gi"),
    ),
    timeout=60,
)
print(result.k8s_job_name)
```

### 2. Jupyter `%%burst` cell magic

```python
%load_ext atlas_burst.magic

%%burst --gpu 1 --memory 16Gi
import torch
print(torch.cuda.is_available())
```

By default `%%burst` checks the local GPU first (via `nvidia-smi`)
and only ships the cell to Nautilus if every local GPU is past the
busy threshold. Useful flags:

| Flag | Behavior |
|---|---|
| `--when-busy` (default) | Burst only if local GPU is busy |
| `--always` | Burst unconditionally |
| `--never` | Run locally unconditionally |
| `--gpu N` | Request `N` GPUs in the burst pod |
| `--cpu X` | CPU request (`"2"`, `"500m"`) |
| `--memory X` | Memory request (`"16Gi"`) |
| `--image IMG` | Container image; default `python:3.12-slim` |
| `--timeout S` | Submit-ack timeout in seconds |
| `--dry-run` | Print the JobDescriptor JSON, don't submit |

Cell source is shipped to the pod via the `ATLAS_BURST_CELL`
environment variable and run with `python -c "$ATLAS_BURST_CELL"`.
Anything that fits in a 1 MiB env var fits in a cell, which is
every realistic notebook cell.

### Configuration

The magic reads two env vars so notebooks stay portable:

```bash
export ATLAS_BURST_NATS_URL="tls://atlas-xxxx.ts.net:443"
export ATLAS_BURST_NATS_CREDS="/path/to/nats.creds"  # optional
```

## What's missing (yet)

| Feature | Status |
|---|---|
| Submit + ack | ✅ |
| Local GPU probe | ✅ |
| Cell magic | ✅ |
| Live log streaming back to the notebook | ⏳ needs controller-side `kubectl logs -f` → NATS bridge |
| Auto-build of a Python image with the user's installed packages | ⏳ |
| File / dataset upload to the burst pod | ⏳ — current pattern: pre-stage on a Nautilus PVC and reference by path |

## Running tests

```bash
cd python
pip install -e '.[ipython,dev]'
pytest -q
```

29 tests exercise descriptor serialization, the GPU probe, the
client (against a `FakeTransport` — no broker required), and the
IPython magic.

## Architecture

See `../docs/design.md` for the full picture and
`../docs/tailscale-funnel.md` for how to expose Atlas's NATS to
Nautilus pods.
