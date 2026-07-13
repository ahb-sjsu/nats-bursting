"""E9: in-situ contended goodput-politeness Pareto on Atlas GPUs.

A competing tenant occupies c(t) of C=2 GV100s on a time-varying profile, so the
guest's available capacity a(t)=C-c(t) is scarce and exogenous (the SCARCITY regime
Prop. 2 targets, unlike the abundance E8). The guest bursts B fixed-work GPU tasks
under one admission policy (naive/static/aimd). aimd probes measured GPU occupancy
(nvidia-smi) with a detection delay and backs off (AIMD). The micro tier -- batch-
probe's ThermalController driven by GPU temperature -- caps guest concurrency to hold
a setpoint while the macro loop admits (two-tier control, both live).

One policy+profile+seed per invocation; writes JSON. See E9_PREREG.md.

Placement: guest tasks go to the least-loaded slot, so n_t<=a(t) => no GPU sharing
and over-admission is exactly 1[n_t>a(t)]. Competitor + guest are memory-light
(~64 MiB/proc) so they never OOM a resident model; ego-stack util is sampled as a
contamination monitor.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import threading
import time

# fixed-WORK guest task: W matmul iters then exit 0 (time grows under contention)
GUEST = (
    "import time,torch\n"
    "d='cuda' if torch.cuda.is_available() else 'cpu'\n"
    "x=torch.randn({n},{n},device=d)\n"
    "for _ in range({work}): x=(x@x).remainder_(7.0).add_(1.0)\n"
    "torch.cuda.synchronize() if d=='cuda' else None\n"
)
# fixed-DURATION competitor: burns for {life}s, counts iters (fewer => slowed = impolite)
COMPET = (
    "import time,torch,json,sys\n"
    "d='cuda' if torch.cuda.is_available() else 'cpu'\n"
    "x=torch.randn({n},{n},device=d)\n"
    "t=time.time()+{life}; k=0\n"
    "while time.time()<t: x=(x@x).remainder_(7.0).add_(1.0); k+=1\n"
    "torch.cuda.synchronize() if d=='cuda' else None\n"
    "open(r'{rf}','w').write(json.dumps({{'iters':k}}))\n"
)
CPU_GUEST = (
    "import numpy as np\n"
    "a=np.random.rand({n},{n}); x=a\n"
    "for _ in range({work}): x=(x@a)%7.0+1.0\n"
)
CPU_COMPET = (
    "import time,numpy as np,json\n"
    "a=np.random.rand({n},{n}); x=a; t=time.time()+{life}; k=0\n"
    "while time.time()<t: x=(x@a)%7.0+1.0; k+=1\n"
    "open(r'{rf}','w').write(json.dumps({{'iters':k}}))\n"
)


def nvidia_util_temp(gpu_ids):
    """-> ({gpu: util%}, {gpu: temp C}); empty on CPU/no-smi."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return {}, {}
    util, temp = {}, {}
    for line in out.strip().splitlines():
        try:
            i, u, t = [x.strip() for x in line.split(",")]
            i = int(i)
            if i in gpu_ids:
                util[i], temp[i] = float(u), float(t)
        except Exception:
            continue
    return util, temp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True,
                    choices=["naive", "static", "aimd", "adaptive"])
    ap.add_argument("--profile", default="square",
                    choices=["square", "poisson", "markov"])
    ap.add_argument("--C", type=int, default=2)                 # capacity (slots)
    ap.add_argument("--burst", type=int, default=24)            # B guest tasks
    ap.add_argument("--work", type=int, default=1200)           # matmul iters/task
    ap.add_argument("--matmul", type=int, default=4096)
    ap.add_argument("--gpus", default="1,0")                    # slot order (free GPU1 first)
    ap.add_argument("--device", default="gpu", choices=["gpu", "cpu"])
    ap.add_argument("--tau", type=int, default=6)               # profile half-period (epochs)
    ap.add_argument("--p-flip", type=float, default=0.1, dest="p_flip",
                    help="markov per-epoch flip prob; tau_c = -1/ln(1-2*p_flip)")
    ap.add_argument("--D", type=int, default=3,
                    help="adaptive: sensing age (epochs) in r_hat=(1-2*p_hat)^D")
    ap.add_argument("--gamma", type=float, default=0.15,
                    help="adaptive: r_hat threshold to run closed-loop vs static fallback")
    ap.add_argument("--c-hi", type=int, default=1, dest="c_hi")
    ap.add_argument("--c-lo", type=int, default=0, dest="c_lo")
    ap.add_argument("--comp-life", type=float, default=8.0, dest="comp_life")
    ap.add_argument("--rate", type=float, default=0.12)         # static submit rate
    ap.add_argument("--alpha", type=int, default=1)             # AIMD additive step
    ap.add_argument("--beta", type=float, default=0.5)          # AIMD backoff factor
    ap.add_argument("--interval", type=float, default=1.0)      # control/monitor epoch
    ap.add_argument("--busy-util", type=float, default=25.0, dest="busy_util")
    ap.add_argument("--thermal", action="store_true")
    ap.add_argument("--setpoint", type=float, default=75.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pybin", default=sys.executable)
    ap.add_argument("--workdir", default="/tmp/e9")
    ap.add_argument("--ego-gpu", type=int, default=0, dest="ego_gpu")  # contamination monitor
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    random.seed(a.seed)
    os.makedirs(a.workdir, exist_ok=True)
    gpu_ids = [int(g) for g in a.gpus.split(",")][: a.C]
    C = a.C
    is_gpu = a.device == "gpu"

    # Capture pre-existing compute-app PIDs (the resident ego stack) so the
    # contamination monitor tracks *those* processes, not our own workload that
    # also lands on the ego GPU.
    ego_pids: set[int] = set()
    if is_gpu:
        try:
            _o = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5).stdout
            ego_pids = {int(x.strip()) for x in _o.splitlines() if x.strip().isdigit()}
        except Exception:
            pass

    def ego_activity():
        """Max SM%% among the pre-existing (ego) PIDs, via nvidia-smi pmon."""
        if not ego_pids:
            return 0.0
        try:
            out = subprocess.run(["nvidia-smi", "pmon", "-c", "1"],
                                 capture_output=True, text=True, timeout=6).stdout
        except Exception:
            return None
        m = 0.0
        for line in out.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            try:
                pid, sm = int(p[1]), p[3]
            except Exception:
                continue
            if pid in ego_pids and sm not in ("-", ""):
                try:
                    m = max(m, float(sm))
                except Exception:
                    pass
        return m

    # ---- micro tier: batch-probe ThermalController on GPU temperature -----------
    thermal = None
    if a.thermal:
        try:
            import batch_probe._thermal_controller as tc

            def _gpu_temp():
                _, temp = nvidia_util_temp(gpu_ids)
                return max(temp.values()) if temp else None

            tc._read_cpu_temp = _gpu_temp  # drive the controller off GPU temp
            from batch_probe import ThermalController

            thermal = ThermalController(
                target_temp=a.setpoint, max_threads=C, min_threads=1,
                poll_interval=1.0, verbose=False,
            )
            thermal.start()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[e9] thermal disabled ({e})\n")
            thermal = None

    def thermal_cap() -> int:
        return thermal.get_threads() if thermal else C

    # ---- process bookkeeping ---------------------------------------------------
    guest: list[tuple[subprocess.Popen, int]] = []   # (proc, slot_gpu)
    comp: list[tuple[subprocess.Popen, int, float]] = []  # (proc, slot_gpu, expiry)
    samples: list[dict] = []
    stop = threading.Event()
    t0 = time.time()

    def live(procs):
        return [x for x in procs if x[0].poll() is None]

    def load_on(g):  # running procs (guest+comp) pinned to slot g
        return sum(1 for p, sg, *_ in live(guest) + live(comp) if sg == g)

    def guest_inflight():
        return len(live(guest))

    def comp_occ():   # ground-truth competitor occupancy c(t)
        return len({sg for _p, sg, *_ in live(comp)})

    def launch_guest():
        # place on least-loaded slot (free GPU preferred -> n<=a means no sharing)
        g = min(gpu_ids, key=load_on)
        code = (GUEST if is_gpu else CPU_GUEST).format(n=a.matmul, work=a.work)
        env = dict(os.environ)
        if is_gpu:
            env["CUDA_VISIBLE_DEVICES"] = str(g)
        else:
            env.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        p = subprocess.Popen([a.pybin, "-c", code], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        guest.append((p, g))

    def launch_comp(g, idx):
        rf = os.path.join(a.workdir, f"comp_{a.policy}_{a.profile}_{a.seed}_{idx}.json")
        code = (COMPET if is_gpu else CPU_COMPET).format(
            n=a.matmul, life=a.comp_life, rf=rf)
        env = dict(os.environ)
        if is_gpu:
            env["CUDA_VISIBLE_DEVICES"] = str(g)
        else:
            env.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        p = subprocess.Popen([a.pybin, "-c", code], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        comp.append((p, g, time.time() + a.comp_life))
        return rf

    # ---- competitor generator (controlled c(t)) --------------------------------
    comp_files: list[str] = []
    comp_idx = [0]
    mk_state = [None]   # markov two-state DTMC state (persists across epochs)

    def c_target(epoch):
        if a.profile == "square":
            return a.c_hi if (epoch // a.tau) % 2 == 0 else a.c_lo
        if a.profile == "markov":
            # symmetric two-state {c_lo,c_hi} DTMC with per-epoch flip prob p_flip:
            # the INFOCOM capacity process. r(D)=(1-2*p_flip)^D, tau_c=-1/ln(1-2*p_flip),
            # so sweeping --p-flip sweeps tau_c and traces Delta(D)=1/2 r(D).
            s = mk_state[0]
            if s is None:
                s = random.random() < 0.5
            elif random.random() < a.p_flip:
                s = not s
            mk_state[0] = s
            return a.c_hi if s else a.c_lo
        # poisson-ish on/off: expected ~c_hi/2, clamped [0, C-1]
        return min(C - 1, max(0, int(round(random.gauss((a.c_hi) * 0.5, 0.7)))))

    def reconcile_comp(epoch):
        want = c_target(epoch)
        have = comp_occ()
        # competitor occupies slots from the *front* (slot0 = free GPU1)
        occupied = {sg for _p, sg, *_ in live(comp)}
        while have < want:
            for g in gpu_ids:
                if g not in occupied:
                    comp_files.append(launch_comp(g, comp_idx[0]))
                    comp_idx[0] += 1
                    occupied.add(g)
                    have += 1
                    break
            else:
                break
        # over-target competitors simply self-expire (fixed life); no kill needed

    # ---- monitor thread --------------------------------------------------------
    def mon():
        while not stop.is_set():
            util, temp = nvidia_util_temp(gpu_ids) if is_gpu else ({}, {})
            ego_util = ego_activity() if is_gpu else None
            n = guest_inflight()
            c = comp_occ()
            samples.append({
                "t": round(time.time() - t0, 2),
                "n": n, "c": c, "a": C - c,
                "over": int(n > (C - c)),
                "cap": thermal_cap(),
                "temp": max(temp.values()) if temp else None,
                "ego_util": ego_util,
            })
            stop.wait(a.interval)

    mt = threading.Thread(target=mon, daemon=True); mt.start()

    # ---- admission loop --------------------------------------------------------
    # aimd and adaptive both start conservative and grow via additive-increase.
    window = 1 if a.policy in ("aimd", "adaptive") else C
    launched = 0
    epoch = 0
    loop0 = time.time()
    congested_epochs = 0

    # ---- regime-adaptive controller online state (§V, Thm 2) -------------------
    # Estimate the flip rate of the (age-D) available-capacity observation stream,
    # form r_hat=(1-2*p_hat)^D, and switch: closed-loop AIMD when r_hat>gamma
    # (trackable), else fall back to the safe static budget floor(a_bar) so we
    # never do worse than static. Mirrors run_adaptive() in tau_sweep.py.
    ad_prev = [None]                 # previous age-D observation a_hat
    ad_flips = [0]; ad_seen = [0]    # flip count / #transitions seen
    ad_abar_sum = [0.0]; ad_abar_n = [0]   # running mean of measured a_hat
    ad_trace: list[dict] = []        # per-epoch (r_hat, p_hat, branch, eff)
    ad_closed = [0]                  # epochs spent in the closed-loop branch

    def gpu_compute_pids():
        """{gpu_index: set(compute PIDs)} via nvidia-smi pmon -- the realistic
        'probe cluster state (incl. other tenants)' census."""
        try:
            out = subprocess.run(["nvidia-smi", "pmon", "-c", "1"],
                                 capture_output=True, text=True, timeout=6).stdout
        except Exception:
            return {}
        census: dict[int, set] = {}
        for line in out.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            try:
                g, pid, typ = int(p[0]), int(p[1]), p[2]
            except Exception:
                continue
            if "C" in typ:  # compute context (ignore pure graphics)
                census.setdefault(g, set()).add(pid)
        return census

    def probe_available():
        """aimd's MEASURED available slots = C - (GPUs occupied by a competitor),
        where a competitor is any compute PID on that GPU that is neither ours nor
        the resident ego stack. Detects co-location a util threshold would miss;
        the pmon sampling + CUDA context startup are the detection delay D."""
        guest_pids = {pp.pid for pp, _sg in live(guest)}
        census = gpu_compute_pids()
        comp_busy = 0
        for g in gpu_ids:
            others = {pid for pid in census.get(g, set())
                      if pid not in guest_pids and pid not in ego_pids}
            if others:
                comp_busy += 1
        return max(0, C - comp_busy)

    while launched < a.burst or guest_inflight() > 0:
        now = time.time()
        reconcile_comp(epoch)

        paced = a.policy == "static"    # rate-paced (trickle) vs window-gated (greedy)
        if a.policy in ("aimd", "adaptive"):
            a_hat = probe_available()
            # advance the AIMD window every epoch (for adaptive this keeps a warm
            # shadow so a switch into the closed-loop branch resumes mid-sawtooth).
            if guest_inflight() > a_hat:              # congestion signal
                window = max(1, math.ceil(a.beta * window))   # multiplicative decrease
                congested_epochs += 1
            else:
                window = min(window + a.alpha, C)             # additive increase

        if a.policy == "aimd":
            eff = min(window, thermal_cap(), max(1, a_hat))
        elif a.policy == "adaptive":
            # online flip-rate estimate on the age-D observation stream a_hat
            if ad_prev[0] is not None:
                ad_flips[0] += int(a_hat != ad_prev[0]); ad_seen[0] += 1
            ad_prev[0] = a_hat
            ad_abar_sum[0] += a_hat; ad_abar_n[0] += 1
            p_hat = ad_flips[0] / max(1, ad_seen[0])
            r_hat = (1.0 - 2.0 * min(p_hat, 0.5)) ** a.D
            if r_hat > a.gamma:                       # trackable -> closed-loop AIMD
                eff = min(window, thermal_cap(), max(1, a_hat))
                branch = "closed"; ad_closed[0] += 1
            else:                                     # untrackable -> static floor(a_bar)
                static_w = max(1, int(math.floor(ad_abar_sum[0] / max(1, ad_abar_n[0]))))
                eff = min(static_w, thermal_cap())
                branch = "static"; paced = True       # trickle like static: never worse
            ad_trace.append({"epoch": epoch, "r_hat": round(r_hat, 4),
                             "p_hat": round(p_hat, 4), "branch": branch, "eff": eff})
        else:  # static, naive
            eff = min(C, thermal_cap())

        if paced:
            # rate-paced: at most one launch per 1/rate s. static keeps its original
            # gate (< C); adaptive's static-fallback is gated by its floor(a_bar) window.
            gate = C if a.policy == "static" else eff
            due = launched < (now - loop0) * a.rate + 1
            if launched < a.burst and due and guest_inflight() < gate:
                launch_guest(); launched += 1
        else:
            while launched < a.burst and guest_inflight() < eff:
                launch_guest(); launched += 1

        stop.wait(a.interval)
        epoch += 1
        if epoch > 4000:  # safety
            break

    wall = time.time() - t0
    stop.set(); mt.join(timeout=2)
    for p, _sg in guest:
        try: p.wait(timeout=30)
        except Exception: pass
    for p, _sg, _e in comp:
        try: p.wait(timeout=30)
        except Exception: pass
    if thermal:
        thermal.stop()

    # ---- metrics ---------------------------------------------------------------
    rows = samples or [{"n": 0, "c": 0, "a": C, "over": 0, "temp": None, "ego_util": None, "cap": C}]
    over = [r["over"] for r in rows]
    rho = sum(over) / len(over)
    temps = [r["temp"] for r in rows if r.get("temp") is not None]
    caps = [r["cap"] for r in rows]
    ego = [r["ego_util"] for r in rows if r.get("ego_util") is not None]
    completed = sum(1 for p, _sg in guest if p.returncode == 0)
    goodput = completed / wall if wall else 0.0
    # competitor iters (impoliteness: fewer = more slowed)
    comp_iters = []
    for rf in comp_files:
        try:
            comp_iters.append(json.load(open(rf)).get("iters"))
        except Exception:
            pass

    res = {
        "policy": a.policy, "profile": a.profile, "seed": a.seed, "C": C,
        "burst": a.burst, "completed": completed, "wall_s": round(wall, 2),
        "goodput_tasks_per_s": round(goodput, 5),
        "over_admission_rho": round(rho, 4),
        "mean_available_abar": round(sum(r["a"] for r in rows) / len(rows), 3),
        "mean_guest_inflight": round(sum(r["n"] for r in rows) / len(rows), 3),
        "thermal_on": bool(thermal),
        "setpoint": a.setpoint if thermal else None,
        "peak_temp": max(temps) if temps else None,
        "mean_temp": round(sum(temps) / len(temps), 1) if temps else None,
        "thermal_throttle_fraction": round(sum(1 for c in caps if c < C) / len(caps), 3),
        "competitor_iters": comp_iters,
        "ego_util_max": max(ego) if ego else None,
        "contaminated": bool(ego and max(ego) > 10.0),
        "n_samples": len(rows),
        "alpha": a.alpha, "beta": a.beta,
    }

    # ---- regime-adaptive diagnostics (which regime it detected, and how) --------
    if a.policy == "adaptive" and ad_trace:
        p_hat = ad_flips[0] / max(1, ad_seen[0])
        r_hat = (1.0 - 2.0 * min(p_hat, 0.5)) ** a.D
        tau_c_hat = (float("inf") if p_hat <= 0
                     else -1.0 / math.log(1 - 2 * min(p_hat, 0.4999)))
        res["adaptive"] = {
            "D": a.D, "gamma": a.gamma,
            "p_hat": round(p_hat, 4), "r_hat": round(r_hat, 4),
            "tau_c_hat": (None if math.isinf(tau_c_hat) else round(tau_c_hat, 2)),
            "frac_closed_loop": round(ad_closed[0] / len(ad_trace), 3),
            "n_decisions": len(ad_trace),
        }
        if a.profile == "markov":
            r_true = (1 - 2 * min(a.p_flip, 0.5)) ** a.D
            res["adaptive"]["p_flip_true"] = a.p_flip
            res["adaptive"]["r_true"] = round(r_true, 4)
            res["adaptive"]["tau_c_true"] = (
                None if a.p_flip <= 0
                else round(-1.0 / math.log(1 - 2 * min(a.p_flip, 0.4999)), 2))

    out_obj = {"experiment": "E9", "cfg": vars(a), "result": res, "samples": samples}
    if a.policy == "adaptive":
        out_obj["adaptive_trace"] = ad_trace
    with open(a.out, "w") as f:
        json.dump(out_obj, f, indent=2)
    print(f"[e9] {a.policy}/{a.profile} seed={a.seed} done={completed}/{a.burst} "
          f"wall={wall:.1f}s goodput={goodput:.4f} rho={rho:.3f} "
          f"peakT={res['peak_temp']} throttle={res['thermal_throttle_fraction']} "
          f"ego_max={res['ego_util_max']} contam={res['contaminated']}", flush=True)


if __name__ == "__main__":
    main()
