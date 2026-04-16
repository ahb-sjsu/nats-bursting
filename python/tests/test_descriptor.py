"""Round-trip and shape tests for JobDescriptor / Resources /
SubmitEnvelope / StatusEvent.

The contract this file enforces is "the JSON on the wire matches
what the Go controller expects". If a field gets renamed, these
tests should be the first thing to fail.
"""

from __future__ import annotations

import json

from nats_bursting.descriptor import (
    JobDescriptor,
    Resources,
    StatusEvent,
    SubmitEnvelope,
)


def test_resources_empty_defaults() -> None:
    r = Resources()
    d = r.to_dict()
    assert d == {
        "cpu": "",
        "memory": "",
        "gpu": 0,
        "ephemeral_storage": "",
    }


def test_resources_roundtrip() -> None:
    r = Resources(cpu="4", memory="16Gi", gpu=2, ephemeral_storage="200Gi")
    restored = json.loads(json.dumps(r.to_dict()))
    assert restored == {
        "cpu": "4",
        "memory": "16Gi",
        "gpu": 2,
        "ephemeral_storage": "200Gi",
    }


def test_jobdescriptor_to_json_matches_go_contract() -> None:
    desc = JobDescriptor(
        name="trainer",
        image="ghcr.io/example/trainer:1.0",
        command=["python", "train.py"],
        args=["--epochs", "5"],
        env={"LOG_LEVEL": "info"},
        resources=Resources(cpu="8", memory="64Gi", gpu=4),
        labels={"owner": "ahbond"},
        backoff_limit=3,
    )
    data = json.loads(desc.to_json())
    assert data["name"] == "trainer"
    assert data["image"] == "ghcr.io/example/trainer:1.0"
    assert data["command"] == ["python", "train.py"]
    assert data["args"] == ["--epochs", "5"]
    assert data["env"] == {"LOG_LEVEL": "info"}
    assert data["resources"]["gpu"] == 4
    assert data["labels"] == {"owner": "ahbond"}
    assert data["backoff_limit"] == 3


def test_jobdescriptor_from_dict_handles_missing_optionals() -> None:
    data = {"name": "x", "image": "alpine"}
    desc = JobDescriptor.from_dict(data)
    assert desc.name == "x"
    assert desc.image == "alpine"
    assert desc.command == []
    assert desc.args == []
    assert desc.env == {}
    assert desc.resources == Resources()
    assert desc.labels == {}
    assert desc.backoff_limit == 0


def test_jobdescriptor_from_dict_preserves_types() -> None:
    data = {
        "name": "x",
        "image": "alpine",
        "backoff_limit": "3",  # type-loose input
        "resources": {"gpu": "1"},
    }
    desc = JobDescriptor.from_dict(data)
    assert desc.backoff_limit == 3
    assert desc.resources.gpu == 1


def test_submit_envelope_serializes_job_id_and_descriptor() -> None:
    env = SubmitEnvelope(
        job_id="abc-123",
        descriptor=JobDescriptor(name="x", image="alpine"),
    )
    data = json.loads(env.to_json())
    assert data["job_id"] == "abc-123"
    assert data["descriptor"]["name"] == "x"


def test_status_event_is_terminal() -> None:
    assert StatusEvent(job_id="x", state="error").is_terminal()
    assert not StatusEvent(job_id="x", state="submitted").is_terminal()


def test_status_event_from_dict_tolerates_missing_fields() -> None:
    ev = StatusEvent.from_dict({})
    assert ev.job_id == ""
    assert ev.state == ""
    assert ev.reason is None
