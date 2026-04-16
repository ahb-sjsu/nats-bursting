"""Tests for the IPython ``%%burst`` magic.

We don't spin up a full IPython shell; we construct ``BurstMagic``
directly and call its ``burst`` method with a synthesized args string.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nats_bursting.client import SubmitResult
from nats_bursting.descriptor import StatusEvent
from nats_bursting.magic import BurstMagic, _build_descriptor, _run_locally

# The magic's IPython decorators require IPython to be importable at
# module load, not at call time. Skip if not installed.
ipython = pytest.importorskip("IPython")


class _FakeShell:
    def __init__(self):
        self.cells: list[str] = []

    def run_cell(self, cell: str):
        self.cells.append(cell)


def _make(client) -> BurstMagic:
    return BurstMagic(shell=_FakeShell(), client=client)


def test_build_descriptor_sets_image_and_cell_env() -> None:
    args = MagicMock()
    args.image = "python:3.12-slim"
    args.cpu = "2"
    args.memory = "4Gi"
    args.gpu = 1
    desc = _build_descriptor("print('hi')", args)
    assert desc.image == "python:3.12-slim"
    assert desc.env["NATS_BURSTING_CELL"] == "print('hi')"
    assert desc.resources.gpu == 1
    assert desc.resources.memory == "4Gi"
    assert desc.labels.get("nats-bursting.io/origin") == "magic"
    # sh -c wrapper so env var interpolation works
    assert desc.command[:2] == ["sh", "-c"]


def test_magic_never_flag_runs_locally_without_client() -> None:
    shell = _FakeShell()
    m = BurstMagic(shell=shell, client=MagicMock(spec_set=["submit_and_wait"]))
    m.burst("--never", "print('local')")
    assert shell.cells == ["print('local')"]


def test_magic_when_busy_skips_burst_if_gpu_has_headroom(capsys) -> None:
    shell = _FakeShell()
    fake_client = MagicMock(spec_set=["submit_and_wait"])
    m = BurstMagic(shell=shell, client=fake_client)
    with patch("nats_bursting.magic.gpu_is_busy", return_value=False):
        m.burst("", "print('local')")
    assert shell.cells == ["print('local')"]
    fake_client.submit_and_wait.assert_not_called()


def test_magic_always_flag_submits_via_client(capsys) -> None:
    fake_client = MagicMock(spec_set=["submit_and_wait"])
    fake_client.submit_and_wait.return_value = SubmitResult(
        job_id="abc",
        status=StatusEvent(job_id="abc", state="submitted", k8s_job="trainer-1"),
    )
    m = _make(fake_client)
    m.burst("--always --gpu 1 --memory 8Gi", "import torch")
    fake_client.submit_and_wait.assert_called_once()
    desc = fake_client.submit_and_wait.call_args.args[0]
    assert desc.resources.gpu == 1
    assert desc.resources.memory == "8Gi"
    out = capsys.readouterr().out
    assert "submitted" in out
    assert "trainer-1" in out


def test_magic_dry_run_emits_json_and_does_not_submit(capsys) -> None:
    fake_client = MagicMock(spec_set=["submit_and_wait"])
    m = _make(fake_client)
    m.burst("--always --dry-run --gpu 2", "print('x')")
    fake_client.submit_and_wait.assert_not_called()
    out = capsys.readouterr().out
    assert '"gpu": 2' in out
    assert '"image"' in out


def test_magic_reports_submission_failure(capsys) -> None:
    fake_client = MagicMock(spec_set=["submit_and_wait"])
    fake_client.submit_and_wait.return_value = SubmitResult(
        job_id="abc",
        status=StatusEvent(job_id="abc", state="error", reason="bad image"),
    )
    m = _make(fake_client)
    m.burst("--always", "print('x')")
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "bad image" in out


def test_run_locally_without_shell_uses_exec() -> None:
    # Defensive branch — should not raise.
    _run_locally("x = 1 + 2", shell=None)
