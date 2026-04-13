"""Tests for ``atlas_burst.client`` using a FakeTransport.

The transport is the only thing that touches NATS, so swapping it
out gives us complete coverage of Client behavior without a broker.
"""

from __future__ import annotations

import json
from typing import Optional

from atlas_burst.client import Client, SubmitResult
from atlas_burst.descriptor import JobDescriptor, Resources


class FakeTransport:
    """Scripted transport.

    ``request_replies``: list of bytes to return from each ``request`` call.
    ``subscribe_replies``: list of bytes (or None) to return from each
    ``subscribe_status`` call. Exhaustion raises to make tests loud.
    """

    def __init__(
        self,
        request_replies: Optional[list[bytes]] = None,
        subscribe_replies: Optional[list[Optional[bytes]]] = None,
        request_error: Optional[Exception] = None,
    ):
        self.request_replies = list(request_replies or [])
        self.subscribe_replies = list(subscribe_replies or [])
        self.request_error = request_error
        self.requests: list[tuple[str, bytes, float]] = []
        self.subscribes: list[tuple[str, float]] = []
        self.closed = False

    def request(self, subject: str, payload: bytes, timeout: float) -> bytes:
        self.requests.append((subject, payload, timeout))
        if self.request_error is not None:
            raise self.request_error
        if not self.request_replies:
            raise AssertionError("FakeTransport.request exhausted")
        return self.request_replies.pop(0)

    def subscribe_status(self, job_id: str, timeout: float) -> Optional[bytes]:
        self.subscribes.append((job_id, timeout))
        if not self.subscribe_replies:
            return None
        return self.subscribe_replies.pop(0)

    def close(self) -> None:
        self.closed = True


def _status_bytes(job_id: str, state: str, **extra) -> bytes:
    d = {"job_id": job_id, "state": state}
    d.update(extra)
    return json.dumps(d).encode("utf-8")


def test_submit_returns_parsed_status_from_request_reply() -> None:
    expected_name = "trainer-xyz"
    fake = FakeTransport(
        request_replies=[_status_bytes("fixed-id", "submitted", k8s_job=expected_name)]
    )
    client = Client(transport=fake)
    result = client.submit(JobDescriptor(name="x", image="alpine"), job_id="fixed-id")
    assert isinstance(result, SubmitResult)
    assert result.accepted
    assert result.k8s_job_name == expected_name
    # Subject and payload look right
    subj, payload, _ = fake.requests[0]
    assert subj == "burst.submit"
    assert b'"fixed-id"' in payload
    assert b'"alpine"' in payload


def test_submit_falls_back_to_subscribe_on_request_failure() -> None:
    fake = FakeTransport(
        request_error=TimeoutError("no responders"),
        subscribe_replies=[_status_bytes("fixed-id", "submitted", k8s_job="y")],
    )
    client = Client(transport=fake)
    result = client.submit(JobDescriptor(name="x", image="alpine"), job_id="fixed-id")
    assert result.accepted
    assert result.k8s_job_name == "y"
    assert fake.subscribes[0][0] == "fixed-id"


def test_submit_reports_unaccepted_when_no_status_returns() -> None:
    fake = FakeTransport(
        request_error=TimeoutError("no responders"),
        subscribe_replies=[None],
    )
    client = Client(transport=fake)
    result = client.submit(JobDescriptor(name="x", image="alpine"), job_id="zzz")
    assert not result.accepted
    assert result.status is None


def test_submit_and_wait_returns_first_ack() -> None:
    fake = FakeTransport(
        request_replies=[_status_bytes("fixed-id", "submitted", k8s_job="n1")]
    )
    client = Client(transport=fake)
    result = client.submit_and_wait(
        JobDescriptor(name="x", image="alpine", resources=Resources(cpu="1")),
        timeout=1.0,
    )
    assert result.accepted
    assert result.k8s_job_name == "n1"


def test_submit_and_wait_polls_until_timeout() -> None:
    # Request returns error status, then all subscribe calls return None.
    fake = FakeTransport(
        request_replies=[_status_bytes("fixed-id", "error", reason="bad image")],
        subscribe_replies=[None, None, None, None, None],
    )
    client = Client(transport=fake)
    result = client.submit_and_wait(
        JobDescriptor(name="x", image="alpine"),
        timeout=0.1,  # deliberately tiny so we give up fast
        poll_interval=0.01,
    )
    # The error status from the initial request is surfaced.
    assert result.status is not None
    assert result.status.state == "error"


def test_context_manager_closes_transport() -> None:
    fake = FakeTransport()
    with Client(transport=fake):
        pass
    assert fake.closed is True


def test_client_uses_configured_submit_subject() -> None:
    fake = FakeTransport(
        request_replies=[_status_bytes("id", "submitted", k8s_job="n")]
    )
    client = Client(transport=fake, submit_subject="custom.subject")
    client.submit(JobDescriptor(name="x", image="alpine"), job_id="id")
    assert fake.requests[0][0] == "custom.subject"
