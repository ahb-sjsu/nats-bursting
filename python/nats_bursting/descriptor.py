"""JobDescriptor dataclass — mirrors the Go struct in
``internal/submitter/submitter.go``.

Keep this in lockstep with the Go version. If the Go struct gains
a field, add it here too (and update serialization tests).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Resources:
    """CPU / memory / GPU / scratch requests.

    All fields use Kubernetes quantity strings (``"4"``, ``"16Gi"``,
    ``"100Gi"``) except ``gpu`` which is an integer count.
    """

    cpu: str = ""
    memory: str = ""
    gpu: int = 0
    ephemeral_storage: str = ""

    def to_dict(self) -> dict:
        return {
            "cpu": self.cpu,
            "memory": self.memory,
            "gpu": self.gpu,
            "ephemeral_storage": self.ephemeral_storage,
        }


@dataclass
class JobDescriptor:
    """High-level description of a one-shot Kubernetes Job.

    Matches the Go ``submitter.JobDescriptor`` field-for-field. JSON
    serialization uses the snake_case keys the Go side expects.
    """

    name: str
    image: str
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    resources: Resources = field(default_factory=Resources)
    labels: dict[str, str] = field(default_factory=dict)
    backoff_limit: int = 0

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "image": self.image,
            "command": list(self.command),
            "args": list(self.args),
            "env": dict(self.env),
            "resources": self.resources.to_dict(),
            "labels": dict(self.labels),
            "backoff_limit": self.backoff_limit,
        }
        return d

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict()).encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "JobDescriptor":
        res = data.get("resources", {}) or {}
        return cls(
            name=data["name"],
            image=data["image"],
            command=list(data.get("command", []) or []),
            args=list(data.get("args", []) or []),
            env=dict(data.get("env", {}) or {}),
            resources=Resources(
                cpu=res.get("cpu", ""),
                memory=res.get("memory", ""),
                gpu=int(res.get("gpu", 0) or 0),
                ephemeral_storage=res.get("ephemeral_storage", ""),
            ),
            labels=dict(data.get("labels", {}) or {}),
            backoff_limit=int(data.get("backoff_limit", 0) or 0),
        )


@dataclass
class SubmitEnvelope:
    """NATS submit-message envelope. Matches Go ``natsbridge.SubmitMessage``."""

    job_id: str
    descriptor: JobDescriptor

    def to_json(self) -> bytes:
        return json.dumps(
            {
                "job_id": self.job_id,
                "descriptor": self.descriptor.to_dict(),
            }
        ).encode("utf-8")


@dataclass
class StatusEvent:
    """NATS status event. Matches Go ``natsbridge.StatusMessage``."""

    job_id: str
    state: str  # "submitted" | "error" | future states
    reason: Optional[str] = None
    k8s_job: Optional[str] = None
    ts: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "StatusEvent":
        return cls(
            job_id=data.get("job_id", ""),
            state=data.get("state", ""),
            reason=data.get("reason"),
            k8s_job=data.get("k8s_job"),
            ts=data.get("ts"),
        )

    def is_terminal(self) -> bool:
        """True if the controller won't publish further events for this job."""
        return self.state in ("error",)


def _require(data: dict, keys: list[str]) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(f"missing required fields: {missing}")


# Compatibility aliases for code that imports the plain dataclass.
_ = asdict
