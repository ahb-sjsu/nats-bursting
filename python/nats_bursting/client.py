"""Synchronous-looking NATS client for the nats-bursting controller.

Wraps ``nats.py`` (which is async) with a synchronous facade suitable
for use from notebooks and scripts. The underlying async loop is
owned by the client and started on demand.

Transport
---------
To keep tests fast and deterministic, all NATS interaction goes
through a ``Transport`` protocol. Production uses ``NATSTransport``;
tests supply a ``FakeTransport`` that echoes scripted replies.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from nats_bursting.descriptor import JobDescriptor, StatusEvent, SubmitEnvelope


@dataclass
class SubmitResult:
    """Returned by ``Client.submit``. A best-effort summary of what
    the controller echoed back on the status subject.
    """

    job_id: str
    status: StatusEvent | None = None

    @property
    def accepted(self) -> bool:
        return self.status is not None and self.status.state == "submitted"

    @property
    def k8s_job_name(self) -> str | None:
        return self.status.k8s_job if self.status else None


class Transport(Protocol):
    """Minimal NATS-like transport.

    ``request`` sends a message on ``subject`` and waits up to
    ``timeout`` seconds for a reply on a reply-inbox. The nats-bursting
    controller is written to publish its first status update back on
    the caller's reply subject when available, falling back to the
    canonical ``burst.status.<job_id>`` subject otherwise.
    """

    def request(self, subject: str, payload: bytes, timeout: float) -> bytes: ...
    def subscribe_status(self, job_id: str, timeout: float) -> bytes | None: ...
    def close(self) -> None: ...


class NATSTransport:
    """Real transport backed by ``nats.py``.

    Starts a background asyncio loop on first use, keeps a persistent
    NATS connection, and exposes blocking ``request`` / ``subscribe``
    helpers.
    """

    def __init__(
        self,
        url: str,
        creds_file: str | None = None,
        status_prefix: str = "burst.status",
        connect_timeout: float = 10.0,
    ):
        self._url = url
        self._creds_file = creds_file
        self._status_prefix = status_prefix
        self._connect_timeout = connect_timeout

        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._nc = None  # type: ignore[var-annotated]

    # ---- lifecycle ---------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None and self._loop.is_running():
            return self._loop
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, name="nats-bursting-nats", daemon=True
        )
        self._loop_thread.start()
        return self._loop

    async def _aconnect(self) -> None:
        import nats  # imported lazily so tests don't need nats-py

        self._nc = await nats.connect(
            self._url,
            user_credentials=self._creds_file if self._creds_file else None,
            connect_timeout=self._connect_timeout,
            name="nats-bursting-py",
        )

    def _connect(self) -> None:
        loop = self._ensure_loop()
        if self._nc is not None:
            return
        future = asyncio.run_coroutine_threadsafe(self._aconnect(), loop)
        future.result(timeout=self._connect_timeout + 2)

    # ---- Transport protocol ------------------------------------------

    def request(self, subject: str, payload: bytes, timeout: float) -> bytes:
        self._connect()
        assert self._nc is not None and self._loop is not None

        async def _do() -> bytes:
            msg = await self._nc.request(subject, payload, timeout=timeout)  # type: ignore[union-attr]
            return msg.data

        return asyncio.run_coroutine_threadsafe(_do(), self._loop).result(
            timeout=timeout + 2
        )

    def subscribe_status(self, job_id: str, timeout: float) -> bytes | None:
        """Block up to ``timeout`` seconds for the first status event
        published on ``<status_prefix>.<job_id>``."""
        self._connect()
        assert self._nc is not None and self._loop is not None
        subj = f"{self._status_prefix}.{job_id}"

        async def _do() -> bytes | None:
            sub = await self._nc.subscribe(subj)  # type: ignore[union-attr]
            try:
                msg = await sub.next_msg(timeout=timeout)
                return msg.data
            except Exception:
                return None
            finally:
                await sub.unsubscribe()

        return asyncio.run_coroutine_threadsafe(_do(), self._loop).result(
            timeout=timeout + 2
        )

    def close(self) -> None:
        if self._nc is not None and self._loop is not None:

            async def _drain() -> None:
                with contextlib.suppress(Exception):
                    await self._nc.drain()  # type: ignore[union-attr]

            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(_drain(), self._loop).result(timeout=5)
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._nc = None
        self._loop = None
        self._loop_thread = None


class Client:
    """High-level nats-bursting submit client.

    Parameters
    ----------
    nats_url:
        NATS URL (``nats://`` or ``tls://``).
    nats_creds:
        Optional path to an NATS credentials file.
    submit_subject:
        Subject the controller subscribes to. Default matches the
        controller's default.
    status_prefix:
        Prefix of the status-event subjects (``<prefix>.<job_id>``).
    transport:
        Inject a custom transport, typically for testing.
    """

    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        nats_creds: str | None = None,
        submit_subject: str = "burst.submit",
        status_prefix: str = "burst.status",
        transport: Transport | None = None,
    ):
        self._submit_subject = submit_subject
        if transport is not None:
            self._transport: Transport = transport
        else:
            self._transport = NATSTransport(
                url=nats_url,
                creds_file=nats_creds,
                status_prefix=status_prefix,
            )

    # ---- core API ----------------------------------------------------

    def submit(
        self, descriptor: JobDescriptor, job_id: str | None = None
    ) -> SubmitResult:
        """Publish a submit message and return the first status event
        (if the controller echoed one within a short window).
        """
        jid = job_id or str(uuid.uuid4())
        envelope = SubmitEnvelope(job_id=jid, descriptor=descriptor)
        try:
            reply = self._transport.request(
                self._submit_subject, envelope.to_json(), timeout=15.0
            )
            status = _parse_status(reply)
        except Exception:
            # Fallback: subscribe for the first status event the
            # controller publishes on the canonical subject.
            reply_bytes = self._transport.subscribe_status(jid, timeout=15.0)
            status = _parse_status(reply_bytes) if reply_bytes else None
        return SubmitResult(job_id=jid, status=status)

    def submit_and_wait(
        self,
        descriptor: JobDescriptor,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
    ) -> SubmitResult:
        """Submit and block until the controller confirms submission
        or the timeout elapses.

        The current controller publishes a single status event on
        successful submission; later controller versions may stream
        additional events (running/succeeded/failed). Callers that
        need terminal-state semantics should subscribe directly via
        ``transport.subscribe_status`` in a loop.
        """
        deadline = time.time() + timeout
        result = self.submit(descriptor)
        if result.accepted:
            return result
        # Keep trying briefly in case the first status message was missed.
        while time.time() < deadline:
            data = self._transport.subscribe_status(
                result.job_id, timeout=poll_interval
            )
            if data:
                status = _parse_status(data)
                if status:
                    return SubmitResult(job_id=result.job_id, status=status)
        return result

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _parse_status(data: bytes | None) -> StatusEvent | None:
    if not data:
        return None
    try:
        return StatusEvent.from_dict(json.loads(data))
    except (ValueError, TypeError):
        return None
