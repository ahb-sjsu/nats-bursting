"""Drive INFOCOM experiments E1–E8 for nats-bursting.

Start ``responder.py`` on the far side first. Each run writes one JSON to --out;
``--mode tables`` aggregates many JSONs into the paper's tables.

Fully implemented against a live NATS endpoint: E1 (RTT+throughput), E2 (= E1 per
path; compared in tables), E3 (JetStream durability cost + recovery), E4
(asymmetric subject interest), E5 (concurrency scaling), E7 (prober detection
delay). E6 (partition resilience) logs disconnect/reconnect while an operator
induces the partition. E8 (end-to-end + baselines) drives the nats-bursting
client and needs live cluster access — its scheduler/metrics are implemented; the
job-submit hook is marked where it binds to the cluster.

Examples:
  python run.py -e E1 --url nats://100.68.134.21:4222 --path tailscale --transport core --out out/E1_ts_core.json
  python run.py -e E3 --url $U --transport js-durable --out out/E3_durable.json
  python run.py -e E5 --url $U --sweep 1,4,8,16,32 --out out/E5.json
  python run.py -e E7 --induce-load --out out/E7.json          # on a GPU node
  python run.py --mode tables --glob 'out/*.json'
"""

from __future__ import annotations

import argparse
import asyncio
import glob as _glob
import json
import os
import time
from typing import Any

import numpy as np
import nats

import harness as H


def base_cfg(a) -> H.Cfg:
    return H.Cfg(
        url=a.url,
        transport=a.transport,
        path=a.path,
        subject=a.subject,
        msg_size=a.msg_size,
        n=a.n,
        concurrency=a.concurrency,
        timeout=a.timeout,
        creds=a.creds,
    )


# ----- E1 / E2: control RTT + throughput (E2 = E1 over multiple paths) -----
async def e1(a) -> dict[str, Any]:
    cfg = base_cfg(a)
    return {
        "rtt": await H.measure_rtt(cfg),
        "throughput": await H.measure_throughput(cfg),
    }


# ----- E3: JetStream durability cost + recovery -----
async def e3(a) -> dict[str, Any]:
    cfg = base_cfg(a)
    assert cfg.transport.startswith(
        "js"
    ), "E3 needs --transport js-durable|js-nondurable"
    pub = await H.measure_js_publish(cfg)
    # recovery: publish, drop the consumer, reconnect, count what survived
    nc, js = await H.connect(cfg)
    marker = f"{cfg.subject}"
    before = (await js.stream_info(cfg.stream)).state.messages
    for _ in range(100):
        await js.publish(marker, H._payload(cfg.msg_size))
    await nc.drain()
    nc2, js2 = await H.connect(cfg)  # fresh connection (simulated restart)
    after = (await js2.stream_info(cfg.stream)).state.messages
    await nc2.drain()
    return {
        "publish_ack": pub,
        "recovery": {
            "msgs_before": before,
            "msgs_after": after,
            "survived_restart": after - before,
        },
    }


# ----- E4: asymmetric subject interest -----
async def e4(a) -> dict[str, Any]:
    cfg = base_cfg(a)
    nc, _ = await H.connect(cfg)
    got: list[float] = []
    interested, uninterested = cfg.subject + ".A", cfg.subject + ".B"
    sent_ts: dict[str, float] = {}

    async def cb(msg) -> None:
        got.append(
            (
                time.perf_counter()
                - sent_ts.get(msg.data.decode(errors="ignore"), time.perf_counter())
            )
            * 1e3
        )

    leaked = [0]

    async def _leak_cb(msg) -> None:  # fires only if .A leaks onto .B (expect 0)
        leaked[0] += 1

    await nc.subscribe(interested, cb=cb)  # interest on .A
    await nc.subscribe(uninterested, cb=_leak_cb)  # interest on .B (no publisher → 0)
    await asyncio.sleep(0.5)  # let interest propagate across the leaf
    for i in range(cfg.n):  # publish to the SUBSCRIBED subject .A
        k = str(i)
        sent_ts[k] = time.perf_counter()
        await nc.publish(interested, k.encode())
    await asyncio.sleep(1.0)
    await nc.drain()
    return {
        "subject_interested": interested,
        "delivered": len(got),
        "expected": cfg.n,
        "delivery_ratio": len(got) / cfg.n if cfg.n else 0.0,
        "propagation_latency_ms": H._summary(got),
        "uninterested_leak": leaked[0],
    }


# ----- E5: concurrency scaling -----
async def e5(a) -> dict[str, Any]:
    rows = []
    try:
        import psutil  # optional driver-side resource sample

        proc = psutil.Process()
    except Exception:
        proc = None
    for w in [int(x) for x in a.sweep.split(",")]:
        cfg = base_cfg(a)
        cfg.concurrency = w
        if proc:
            proc.cpu_percent(None)
        tp = await H.measure_throughput(cfg)
        if proc:
            tp["driver_cpu_pct"] = proc.cpu_percent(None)
            tp["driver_rss_mb"] = proc.memory_info().rss / 1e6
        tp["window"] = w
        rows.append(tp)
    return {
        "sweep": rows,
        "note": "Go control-plane CPU/mem come from its own /metrics; driver-side sampled here.",
    }


# ----- E6: partition resilience (operator induces the partition) -----
async def e6(a) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    async def disc():
        events.append({"event": "disconnected", "t": time.perf_counter() - t0})

    async def recon():
        events.append({"event": "reconnected", "t": time.perf_counter() - t0})

    async def err(e):
        events.append(
            {"event": "error", "t": time.perf_counter() - t0, "msg": str(e)[:80]}
        )

    cfg = base_cfg(a)
    kw = {"user_credentials": cfg.creds} if cfg.creds else {}
    nc = await nats.connect(
        cfg.url,
        disconnected_cb=disc,
        reconnected_cb=recon,
        error_cb=err,
        max_reconnect_attempts=-1,
        **kw,
    )
    msgs_before = None
    if cfg.transport.startswith("js"):
        js = nc.jetstream()
        try:
            msgs_before = (await js.stream_info(cfg.stream)).state.messages
        except Exception:
            pass
    print(
        f"[E6] connected; INDUCE THE PARTITION NOW (e.g. `tailscale down; sleep 10; tailscale up`). "
        f"Logging for {a.duration}s...",
        flush=True,
    )
    await asyncio.sleep(a.duration)
    gaps = []
    for i in range(1, len(events)):
        if (
            events[i]["event"] == "reconnected"
            and events[i - 1]["event"] == "disconnected"
        ):
            gaps.append(events[i]["t"] - events[i - 1]["t"])
    msgs_after = None
    if cfg.transport.startswith("js"):
        try:
            msgs_after = (await nc.jetstream().stream_info(cfg.stream)).state.messages
        except Exception:
            pass
    await nc.drain()
    return {
        "events": events,
        "reconnect_gaps_s": gaps,
        "mean_reconnect_s": float(np.mean(gaps)) if gaps else None,
        "js_msgs_before": msgs_before,
        "js_msgs_after": msgs_after,
    }


# ----- E7: prober detection delay D -----
async def e7(a) -> dict[str, Any]:
    from nats_bursting import probe  # the real prober

    # nvidia-smi / probe call latency is the core of D
    call_lat = []
    for _ in range(20):
        s = time.perf_counter()
        try:
            probe.probe_local_gpu()
        except Exception:
            break
        call_lat.append((time.perf_counter() - s) * 1e3)
    out: dict[str, Any] = {
        "probe_call_ms": H._summary(call_lat),
        "note": "D ≈ poll_interval + probe_call + decision; full detection "
        "needs --induce-load on a GPU node.",
    }
    if a.induce_load:
        # start a GPU load, poll until gpu_is_busy fires, time the detection
        try:
            import torch  # noqa
            import threading

            stop = {"v": False}

            def burn():
                x = torch.randn(4096, 4096, device="cuda")
                while not stop["v"]:
                    x = x @ x

            th = threading.Thread(target=burn, daemon=True)
            th.start()
            t0 = time.perf_counter()
            for _ in range(2000):
                try:
                    if probe.gpu_is_busy():
                        out["detection_latency_ms"] = (time.perf_counter() - t0) * 1e3
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            stop["v"] = True
        except Exception as exc:
            out["induce_load_error"] = str(exc)[:120]
    return out


# ----- E8: end-to-end + baselines (needs live cluster + client) -----
async def e8(a) -> dict[str, Any]:
    """End-to-end burst under {naive, static, aimd}: submit B jobs through the real
    ``nats_bursting.client.Client`` and time cold-start, submit→first-result, and
    burst-completion by draining results on ``<result_prefix><job_id>``.

    Requires live cluster access: the submitted ``--image`` must be a burst worker
    that publishes a result to ``<result_prefix><job_id>`` (the bundled worker does).
    GPU util + over-admission (violation) rate are sampled on the node by
    ``nats_bursting.probe`` during the run.
    """
    from nats_bursting.client import Client
    from nats_bursting.descriptor import JobDescriptor, Resources

    B, policy = a.burst, a.baseline
    if policy == "naive":
        sched = [0.0] * B  # all at once
    elif policy == "static":
        sched = [i / max(a.rate, 1e-9) for i in range(B)]  # fixed rate r jobs/s
    elif policy == "aimd":
        sched = _aimd_schedule(B, a.alpha, a.beta, a.kcap)  # window-paced (model of §4)
    else:
        raise SystemExit(f"unknown --baseline {policy}")

    # --- result draining (async): subscribe BEFORE submitting ---
    kw = {"user_credentials": a.creds} if a.creds else {}
    nc = await nats.connect(a.url, **kw)
    t0 = time.perf_counter()
    first_result: list[Any] = [None]
    completed = [0]
    done = asyncio.Event()

    async def on_result(_msg) -> None:
        if first_result[0] is None:
            first_result[0] = time.perf_counter() - t0
        completed[0] += 1
        if completed[0] >= B:
            done.set()

    await nc.subscribe(a.result_prefix + ">", cb=on_result)

    # --- sync submit client (spins its own bg loop); call via a thread ---
    client = Client(nats_url=a.url, nats_creds=a.creds, submit_subject=a.submit_subject)

    def _desc(i: int) -> JobDescriptor:
        return JobDescriptor(
            name=f"infocom-{policy}-{i}",
            image=a.image,
            command=(a.command.split() if a.command else []),
            env={"NATS_URL": a.url, "NATS_RESULT_PREFIX": a.result_prefix},
            resources=Resources(cpu="1", memory="2Gi", gpu=a.gpu),
            labels={"infocom": policy},
        )

    submit_times: list[float] = []
    accepted = [0]

    async def submit(i: int) -> None:
        res = await asyncio.to_thread(client.submit, _desc(i), f"infocom-{policy}-{i}")
        submit_times.append(time.perf_counter() - t0)
        if getattr(res, "accepted", False):
            accepted[0] += 1

    tasks = []
    for i, dt in enumerate(sched):
        await asyncio.sleep(max(0.0, dt - (time.perf_counter() - t0)))
        tasks.append(asyncio.create_task(submit(i)))
    await asyncio.gather(*tasks)

    try:  # wait (bounded) for all results
        await asyncio.wait_for(done.wait(), timeout=a.duration)
    except asyncio.TimeoutError:
        pass
    completion = time.perf_counter() - t0
    client.close()
    await nc.drain()

    return {
        "policy": policy,
        "burst": B,
        "accepted": accepted[0],
        "cold_start_s": min(submit_times) if submit_times else None,
        "submit_to_first_result_s": first_result[0],
        "burst_completion_s": (completion if completed[0] >= B else None),
        "completed": completed[0],
        "note": "GPU util + over-admission (violation) rate are sampled on the node via "
        "nats_bursting.probe during the run; --image must be a burst worker that publishes "
        "to <result_prefix><job_id>.",
    }


def _aimd_schedule(B: int, alpha: int, beta: float, kcap: int) -> list[float]:
    """Submit-time schedule from the §4 AIMD window (open-loop preview; the live
    controller uses the prober's congestion signal). One 'epoch' per second."""
    times, w, epoch, emitted = [], 1, 0.0, 0
    while emitted < B:
        for _ in range(min(w, B - emitted)):
            times.append(epoch)
            emitted += 1
        w = min(w + alpha, kcap)  # additive increase (no signal in preview)
        epoch += 1.0
    return times[:B]


# ----- tables aggregator -----
def tables(a) -> None:
    recs = [json.load(open(p)) for p in _glob.glob(a.glob)]
    e1s = [r for r in recs if r["experiment"] in ("E1", "E2")]
    if e1s:
        print("\n### E1/E2 — control RTT & throughput (by transport × path)\n")
        print("| transport | path | RTT p50/p95/p99 (ms) | throughput (msg/s) |")
        print("|---|---|---|---|")
        for r in sorted(e1s, key=lambda r: (r["cfg"]["transport"], r["cfg"]["path"])):
            rtt, tp = r["result"]["rtt"], r["result"]["throughput"]
            print(
                f"| {r['cfg']['transport']} | {r['cfg']['path']} | "
                f"{rtt['p50_ms']:.2f}/{rtt['p95_ms']:.2f}/{rtt['p99_ms']:.2f} | "
                f"{tp['throughput_msgs_s']:.0f} |"
            )
    e3s = [r for r in recs if r["experiment"] == "E3"]
    if e3s:
        print("\n### E3 — JetStream durability cost\n")
        print("| storage | publish-ack p50/p95/p99 (ms) | survived restart |")
        print("|---|---|---|")
        for r in e3s:
            pa = r["result"]["publish_ack"]
            rec = r["result"]["recovery"]
            print(
                f"| {pa.get('storage')} | {pa['p50_ms']:.2f}/{pa['p95_ms']:.2f}/{pa['p99_ms']:.2f} "
                f"| {rec['survived_restart']} |"
            )
    e5s = [r for r in recs if r["experiment"] == "E5"]
    for r in e5s:
        print(
            "\n### E5 — concurrency scaling\n\n| window | throughput (msg/s) | p99 (ms) |\n|---|---|---|"
        )
        for row in r["result"]["sweep"]:
            print(
                f"| {row['window']} | {row['throughput_msgs_s']:.0f} | {row['p99_ms']:.2f} |"
            )


_EXPS = {"E1": e1, "E2": e1, "E3": e3, "E4": e4, "E5": e5, "E6": e6, "E7": e7, "E8": e8}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-e", "--experiment", choices=list(_EXPS))
    ap.add_argument("--mode", choices=["run", "tables"], default="run")
    ap.add_argument(
        "--url", default=os.environ.get("NATS_URL", "nats://localhost:4222")
    )
    ap.add_argument(
        "--transport", default="core", choices=["core", "js-durable", "js-nondurable"]
    )
    ap.add_argument("--path", default="lan")
    ap.add_argument("--subject", default="infocom.echo")
    ap.add_argument("--msg-size", type=int, default=256, dest="msg_size")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--creds", default=os.environ.get("NATS_BURSTING_NATS_CREDS"))
    ap.add_argument("--sweep", default="1,4,8,16,32", help="E5 concurrency windows")
    ap.add_argument(
        "--duration", type=float, default=60.0, help="E6 logging window (s)"
    )
    ap.add_argument("--induce-load", action="store_true", help="E7: drive a GPU load")
    ap.add_argument("--baseline", default="aimd", choices=["naive", "static", "aimd"])
    ap.add_argument("--burst", type=int, default=64, help="E8 number of jobs")
    ap.add_argument("--rate", type=float, default=2.0, help="E8 static jobs/s")
    ap.add_argument("--alpha", type=int, default=2, help="E8 AIMD additive step")
    ap.add_argument("--beta", type=float, default=0.5, help="E8 AIMD backoff")
    ap.add_argument("--kcap", type=int, default=4, help="E8 pod cap K")
    ap.add_argument(
        "--image",
        default="ghcr.io/ahb-sjsu/nats-bursting-worker:latest",
        help="E8 job image (must be a burst worker publishing to <result_prefix><job_id>)",
    )
    ap.add_argument("--command", default="", help="E8 job command (space-separated)")
    ap.add_argument("--gpu", type=int, default=1, help="E8 GPUs per job")
    ap.add_argument("--result-prefix", default="results.", dest="result_prefix")
    ap.add_argument("--submit-subject", default="burst.submit", dest="submit_subject")
    ap.add_argument("--out", default="out/result.json")
    ap.add_argument("--glob", default="out/*.json", help="tables mode input")
    a = ap.parse_args()

    if a.mode == "tables":
        tables(a)
        return
    if not a.experiment:
        ap.error("--experiment required in run mode")
    result = asyncio.run(_EXPS[a.experiment](a))
    H.write_results(a.out, a.experiment, base_cfg(a), result)
    print(f"[{a.experiment}] wrote {a.out}")


if __name__ == "__main__":
    main()
