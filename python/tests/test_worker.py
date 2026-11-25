"""Worker handler dispatch: sync handlers must not hold the event loop."""

from __future__ import annotations

import asyncio
import functools
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

from nats_bursting.worker import Worker


class FakeNC:
    def __init__(self):
        self.published = []

    async def publish(self, subject, data):
        self.published.append((subject, json.loads(data.decode())))


def _task(task_id, task_type="work", **extra):
    return json.dumps({"id": task_id, "type": task_type, **extra}).encode()


async def _ticks_during(coro, period=0.01):
    """Run ``coro`` and count how often the event loop got to run meanwhile."""
    ticks = 0
    done = False

    async def ticker():
        nonlocal ticks
        while not done:
            await asyncio.sleep(period)
            ticks += 1

    t = asyncio.create_task(ticker())
    await coro
    done = True
    await t
    return ticks


def _slow(seen):
    def slow(task):
        seen["thread"] = threading.current_thread()
        time.sleep(0.3)
        return {"ok": True}

    return slow


def test_sync_handler_leaves_the_loop_free():
    seen = {}

    async def main():
        nc = FakeNC()
        w = Worker(handlers={"work": _slow(seen)})
        ticks = await _ticks_during(w._handle(nc, _task("a")))
        return nc, ticks

    nc, ticks = asyncio.run(main())
    # 0.3 s of handler at a 10 ms tick: a blocked loop gives 0 or 1 tick.
    assert ticks >= 10
    assert seen["thread"] is not threading.main_thread()
    subject, result = nc.published[0]
    assert subject == "results.a"
    assert result["ok"] is True and result["task_id"] == "a"


def test_opt_out_runs_on_the_loop_thread():
    seen = {}

    async def main():
        nc = FakeNC()
        w = Worker(handlers={"work": _slow(seen)}, handler_thread=False)
        ticks = await _ticks_during(w._handle(nc, _task("a")))
        return nc, ticks

    nc, ticks = asyncio.run(main())
    assert ticks <= 1
    assert seen["thread"] is threading.main_thread()
    assert nc.published[0][1]["ok"] is True


def test_env_opt_out(monkeypatch):
    monkeypatch.setenv("NATS_HANDLER_THREAD", "0")
    assert Worker(handlers={}).handler_thread is False
    monkeypatch.delenv("NATS_HANDLER_THREAD")
    assert Worker(handlers={}).handler_thread is True


def test_sync_handlers_run_one_at_a_time():
    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def slow(task):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return {"n": task["n"]}

    async def main():
        nc = FakeNC()
        w = Worker(handlers={"work": slow})
        await asyncio.gather(*(w._handle(nc, _task(i, n=i)) for i in range(4)))
        return nc

    nc = asyncio.run(main())
    assert state["peak"] == 1
    assert sorted(r["n"] for _, r in nc.published) == [0, 1, 2, 3]


def test_async_handler_and_sync_wrappers_around_async():
    async def ahandler(task, scale=1):
        await asyncio.sleep(0)
        return {"n": task["n"] * scale}

    async def main():
        nc = FakeNC()
        w = Worker(
            handlers={
                "plain": ahandler,
                "partial": functools.partial(ahandler, scale=10),
                "lambda": lambda task: ahandler(task, scale=100),
            }
        )
        await w._handle(nc, _task("p", "plain", n=2))
        await w._handle(nc, _task("q", "partial", n=2))
        await w._handle(nc, _task("r", "lambda", n=2))
        return nc

    nc = asyncio.run(main())
    assert [r["n"] for _, r in nc.published] == [2, 20, 200]


def test_exception_in_thread_becomes_error_result():
    def boom(task):
        raise ValueError("nope")

    acks = []

    async def ack(ok):
        acks.append(ok)

    async def main():
        nc = FakeNC()
        w = Worker(handlers={"work": boom})
        await w._handle(nc, _task("a"), ack)
        await w._handle(nc, _task("b", "missing"), ack)
        return nc

    nc = asyncio.run(main())
    assert nc.published[0][1]["error"] == "nope"
    # The kept part of the traceback is its end, whatever the path length.
    assert nc.published[0][1]["traceback"].rstrip().endswith("ValueError: nope")
    assert len(nc.published[0][1]["traceback"]) <= 1000
    assert "no handler" in nc.published[1][1]["error"]
    assert acks == [True, True]


def test_none_return_becomes_empty_result():
    async def main():
        nc = FakeNC()
        w = Worker(handlers={"work": lambda task: None})
        await w._handle(nc, _task("a"))
        return nc

    nc = asyncio.run(main())
    assert nc.published[0][1]["task_id"] == "a"


# --- stopping in core-NATS mode: nothing another worker could take is lost ---


class FakeSub:
    """A subscription as nats-py runs one: messages go through the callback one at a time; drain() takes no new
    ones and returns when those already delivered have been through the callback."""

    def __init__(self, nc, subject, cb):
        self.nc, self.subject, self.cb = nc, subject, cb
        self.queue = asyncio.Queue()
        self.subscribed = True
        self.task = asyncio.create_task(self._pump())

    async def _pump(self):
        while True:
            msg = await self.queue.get()
            try:
                await self.cb(msg)
            finally:
                self.queue.task_done()

    async def drain(self):
        self.subscribed = False
        await self.queue.join()
        self.task.cancel()


class FakeMsg:
    def __init__(self, subject, data):
        self.subject, self.data, self.reply, self.headers = subject, data, "", None


class FakeGroupNC(FakeNC):
    """One worker's connection. A publish on the task subject is delivered back to this worker while it is still
    subscribed (a queue group may pick the sender) and counts as taken by another worker once it is not.
    """

    def __init__(self):
        super().__init__()
        self.subs = {}
        self.elsewhere = []

    async def subscribe(self, subject, queue=None, cb=None):
        self.subs[subject] = FakeSub(self, subject, cb)
        return self.subs[subject]

    async def publish(self, subject, data, reply="", headers=None):
        sub = self.subs.get(subject)
        if sub is None:
            await super().publish(subject, data)
        elif sub.subscribed:
            sub.queue.put_nowait(FakeMsg(subject, data))
        else:
            self.elsewhere.append(json.loads(data.decode())["id"])


@pytest.mark.skipif(
    sys.platform == "win32", reason="needs POSIX signals on the event loop"
)
def test_stop_finishes_the_running_task_and_hands_the_queued_ones_back():
    started = threading.Event()
    release = threading.Event()

    def slow(task):
        started.set()
        assert release.wait(10)
        return {"n": task["n"]}

    async def main():
        nc = FakeGroupNC()
        w = Worker(handlers={"work": slow}, subjects=["tasks.work"], durable=False)
        run = asyncio.create_task(w._run_core(nc))
        while "tasks.work" not in nc.subs:
            await asyncio.sleep(0.01)
        for i in range(4):
            await nc.publish("tasks.work", _task(f"t{i}", n=i))
        await asyncio.to_thread(started.wait, 10)
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.2)
        assert not run.done()  # still running t0: the stop waits for it
        assert nc.published == []
        release.set()
        await asyncio.wait_for(run, 10)
        return nc

    nc = asyncio.run(main())
    assert [(s, r["n"]) for s, r in nc.published] == [("results.t0", 0)]
    assert nc.elsewhere == ["t1", "t2", "t3"]
    assert not nc.subs["tasks.work"].subscribed


def _nats_server():
    return shutil.which("nats-server") or next(
        (p for p in [os.path.expanduser("~/bin/nats-server")] if os.path.exists(p)),
        None,
    )


WORKER_SCRIPT = """
import sys, time
from nats_bursting.worker import run_worker

def slow(task):
    print("START", task["id"], flush=True)
    time.sleep(float(task.get("seconds", 1.0)))
    return {"n": task["n"]}

run_worker({"work": slow}, nats_url=sys.argv[1], subjects=["rt.tasks"], consumer_group="rt",
           result_prefix="rt.results.", durable=False)
"""


def _wait_for(path, text, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(path) and text in pathlib.Path(path).read_text("utf-8"):
            return
        time.sleep(0.05)
    raise AssertionError(f"{text!r} never appeared in {path}")


@pytest.mark.skipif(_nats_server() is None, reason="no nats-server binary")
def test_sigterm_loses_no_task_with_a_real_server(tmp_path):
    """Two worker processes on a real nats-server. A takes four tasks alone (one running, three queued in its
    client), B joins, A gets SIGTERM: A finishes its task and exits 0, B runs the three handed back.
    """
    import nats

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"nats://127.0.0.1:{port}"
    script = tmp_path / "w.py"
    script.write_text(WORKER_SCRIPT)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    procs = []

    def start_worker(name):
        with open(tmp_path / f"{name}.log", "w", encoding="utf-8") as out:
            p = subprocess.Popen(
                [sys.executable, "-u", str(script), url],
                env=dict(env, HOSTNAME=name),
                stdout=out,
                stderr=out,
            )
        procs.append(p)
        _wait_for(str(tmp_path / f"{name}.log"), "worker ready")
        return p

    server = subprocess.Popen(
        [_nats_server(), "-a", "127.0.0.1", "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:

        async def main():
            for _ in range(100):
                try:
                    nc = await nats.connect(url, allow_reconnect=False)
                    break
                except Exception:
                    await asyncio.sleep(0.05)
            results = []

            async def on_result(msg):
                results.append(json.loads(msg.data.decode()))

            await nc.subscribe("rt.results.*", cb=on_result)
            a = await asyncio.to_thread(start_worker, "A")
            for i in range(4):
                await nc.publish(
                    "rt.tasks", _task(f"t{i}", n=i, seconds=1.5 if i == 0 else 0.1)
                )
            await nc.flush()
            await asyncio.to_thread(_wait_for, str(tmp_path / "A.log"), "START t0")
            await asyncio.to_thread(start_worker, "B")
            a.send_signal(signal.SIGTERM)
            for _ in range(200):
                if len(results) >= 4:
                    break
                await asyncio.sleep(0.05)
            rc = await asyncio.to_thread(a.wait, 10)
            await asyncio.sleep(0.3)  # a duplicate result would arrive here
            await nc.close()
            return results, rc

        results, rc = asyncio.run(main())
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                p.wait(10)
        server.terminate()
        server.wait(10)
    assert rc == 0
    assert sorted((r["task_id"], r["worker"]) for r in results) == [
        ("t0", "A"),
        ("t1", "B"),
        ("t2", "B"),
        ("t3", "B"),
    ]
    assert all("error" not in r for r in results)
    a_log = (tmp_path / "A.log").read_text("utf-8")
    assert a_log.count("handed a queued task back") == 3
