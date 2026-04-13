"""Probe local GPU state to decide whether to burst.

We use ``nvidia-smi`` output when available (most portable — avoids
making ``torch`` a mandatory dependency). Falls back to "assume
available" if nvidia-smi isn't on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class GPUState:
    """Snapshot of one GPU."""

    index: int
    utilization_pct: float  # 0..100
    memory_used_mib: int
    memory_total_mib: int

    @property
    def memory_pct(self) -> float:
        if self.memory_total_mib == 0:
            return 0.0
        return 100.0 * self.memory_used_mib / self.memory_total_mib


def probe_local_gpu(
    nvidia_smi: str = "nvidia-smi", timeout: int = 10
) -> list[GPUState]:
    """Return the current state of each local GPU.

    Returns an empty list when nvidia-smi is unavailable or errors.
    """
    if shutil.which(nvidia_smi) is None:
        return []
    try:
        out = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=index,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        ).stdout
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return []
    return _parse_nvidia_smi(out)


def _parse_nvidia_smi(out: str) -> list[GPUState]:
    states: list[GPUState] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            states.append(
                GPUState(
                    index=int(parts[0]),
                    utilization_pct=float(parts[1]),
                    memory_used_mib=int(parts[2]),
                    memory_total_mib=int(parts[3]),
                )
            )
        except ValueError:
            continue
    return states


def gpu_is_busy(
    util_threshold_pct: float = 85.0,
    memory_threshold_pct: float = 85.0,
    states: Optional[list[GPUState]] = None,
) -> bool:
    """Decision helper used by the `%%burst` magic.

    Returns True when *every* local GPU exceeds at least one of the
    thresholds — i.e. "there is nowhere local left to land a new
    workload, bursting is justified". Returns False when any GPU has
    headroom, or when no GPUs are reported.

    Callers with more nuanced requirements can call ``probe_local_gpu``
    directly and decide themselves.
    """
    if states is None:
        states = probe_local_gpu()
    if not states:
        return False
    for s in states:
        if (
            s.utilization_pct < util_threshold_pct
            and s.memory_pct < memory_threshold_pct
        ):
            # Found one with headroom — no need to burst.
            return False
    return True
