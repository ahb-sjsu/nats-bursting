"""Worker handler dispatch: sync handlers must not hold the event loop."""

from __future__ import annotations

import asyncio
import functools
import json
import threading
import time

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
    assert "ValueError" in nc.published[0][1]["traceback"]
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
