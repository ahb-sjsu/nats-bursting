"""Tests for ``atlas_burst.probe``.

No real nvidia-smi is invoked; we exercise the parser and the
threshold logic directly.
"""

from __future__ import annotations

from atlas_burst.probe import GPUState, _parse_nvidia_smi, gpu_is_busy


def test_parse_nvidia_smi_typical() -> None:
    out = "0, 85, 30000, 32000\n" "1, 10, 1000, 32000\n"
    states = _parse_nvidia_smi(out)
    assert len(states) == 2
    assert states[0].index == 0
    assert states[0].utilization_pct == 85.0
    assert states[0].memory_used_mib == 30000
    assert abs(states[0].memory_pct - 93.75) < 1e-6
    assert states[1].utilization_pct == 10.0


def test_parse_nvidia_smi_rejects_malformed_rows() -> None:
    out = "0, oops, x, x\n1, 50, 1000, 2000\n"
    states = _parse_nvidia_smi(out)
    assert len(states) == 1
    assert states[0].index == 1


def test_gpu_is_busy_no_gpus_returns_false() -> None:
    # On a CPU-only machine there's nowhere busy by definition;
    # the magic then falls back to "no burst needed".
    assert gpu_is_busy(states=[]) is False


def test_gpu_is_busy_any_free_gpu_returns_false() -> None:
    states = [
        GPUState(0, utilization_pct=95, memory_used_mib=31000, memory_total_mib=32000),
        GPUState(1, utilization_pct=10, memory_used_mib=2000, memory_total_mib=32000),
    ]
    assert gpu_is_busy(states=states) is False


def test_gpu_is_busy_all_busy_returns_true() -> None:
    states = [
        GPUState(0, utilization_pct=95, memory_used_mib=31000, memory_total_mib=32000),
        GPUState(1, utilization_pct=90, memory_used_mib=30000, memory_total_mib=32000),
    ]
    assert gpu_is_busy(states=states) is True


def test_gpu_is_busy_memory_pressure_alone_triggers() -> None:
    # GPU util low but memory full → still "busy" from an allocator's perspective
    states = [
        GPUState(0, utilization_pct=5, memory_used_mib=31500, memory_total_mib=32000),
    ]
    assert gpu_is_busy(states=states, util_threshold_pct=85, memory_threshold_pct=85)


def test_gpu_is_busy_threshold_customization() -> None:
    states = [
        GPUState(0, utilization_pct=50, memory_used_mib=16000, memory_total_mib=32000),
    ]
    assert not gpu_is_busy(
        states=states, util_threshold_pct=85, memory_threshold_pct=85
    )
    # Lower the bar enough and the same state is "busy":
    assert gpu_is_busy(states=states, util_threshold_pct=40, memory_threshold_pct=40)
