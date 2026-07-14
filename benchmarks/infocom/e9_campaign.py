"""E9 campaign driver (run ON Atlas under nohup). Randomized-interleaved trial
order per E9_PREREG.md; each trial is one e9_contended.py invocation. Idempotent:
skips trials whose JSON already exists. Progress -> /tmp/e9/campaign.log.
"""

from __future__ import annotations

import itertools
import os
import random
import subprocess
import time

PY = "/home/claude/env/bin/python3"
SCRIPT = "/home/claude/e9/e9_contended.py"
OUT = "/tmp/e9/run"
WD = "/tmp/e9/wd"

# Runtime knobs (set by launch_adaptive.sh; safe defaults for a manual run):
#   E9_GPUS   slot order for guest tasks, e.g. "0,1" if GPU0 is the free one.
#   E9_TRIALS which subset to run: new|markov|adaptive|all (default: new = the
#             adaptive rows + markov tau_c sweep this port adds, i.e. the least
#             GPU time and no re-running of already-published square/poisson cells).
GPUS = os.environ.get("E9_GPUS", "1,0")
SELECT = os.environ.get("E9_TRIALS", "new")
BURST = os.environ.get("E9_BURST", "16")   # guest tasks/trial (lower => shorter run)
WORK = os.environ.get("E9_WORK", "1000")   # matmul iters/task (lower => shorter run)

POLICIES = ["naive", "static", "aimd", "adaptive"]
PROFILES = ["square", "poisson"]
SEEDS = [42, 43, 44, 45]
COMMON = ["--burst", BURST, "--work", WORK, "--matmul", "4096",
          "--comp-life", "25", "--tau", "25", "--interval", "1",
          "--rate", "0.06", "--gpus", GPUS]

# markov-profile overrides: the DTMC must be *realized* on the GPU for the
# Delta(D)=1/2 r(D) sweep to be meaningful. A longer epoch lets the competitor
# launch/kill actuate within an epoch (CUDA init is seconds), and a long comp_life
# hands occupancy control fully to the (now-symmetric) reconcile_comp rather than to
# fixed-life self-expiry. See ADAPTIVE_CURVE_FINDINGS.md.
MK_INTERVAL = os.environ.get("E9_MK_INTERVAL", "2")
MK_COMPLIFE = os.environ.get("E9_MK_COMPLIFE", "600")

# markov tau_c sweep: --p-flip sweeps tau_c=-1/ln(1-2p), landing in-situ points on
# the Delta(D)=1/2 r(D) law (Fig tau_sweep). adaptive is the marquee controller;
# aimd/static are the envelope it must track (never below static, near aimd when
# trackable). Fewer seeds here to bound GPU wall-clock.
MARKOV_POLICIES = ["adaptive", "aimd", "static"]
MARKOV_PFLIP = [0.01, 0.03, 0.08, 0.15, 0.40]
MARKOV_SEEDS = [42, 43]

# trials are 5-tuples: (policy, profile, seed, thermal, p_flip|None)
trials = [(p, pr, s, False, None)
          for p, pr, s in itertools.product(POLICIES, PROFILES, SEEDS)]
trials += [("aimd", "square", s, True, None) for s in (42, 43)]   # thermal demo (H4)
trials += [("naive", "square", s, True, None) for s in (42,)]     # thermal under naive too
trials += [(p, "markov", s, False, pf)                            # tau_c sweep
           for p in MARKOV_POLICIES for pf in MARKOV_PFLIP for s in MARKOV_SEEDS]


def _keep(pol: str, prof: str, pflip) -> bool:
    if SELECT == "all":
        return True
    if SELECT == "markov":
        return prof == "markov"
    if SELECT == "adaptive":
        return pol == "adaptive"
    # "new": the two things this port adds -- adaptive rows + the markov tau_c sweep
    return pol == "adaptive" or prof == "markov"


trials = [t for t in trials if _keep(t[0], t[1], t[4])]
random.Random(2027).shuffle(trials)                            # interleaved order


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(WD, exist_ok=True)
    logf = open("/tmp/e9/campaign.log", "a")

    def L(m: str) -> None:
        logf.write(m + "\n"); logf.flush()
        print(m, flush=True)

    L(f"[campaign] {len(trials)} trials (E9_TRIALS={SELECT}, E9_GPUS={GPUS}) "
      f"@ {time.strftime('%H:%M:%S')}")
    for i, (pol, prof, seed, therm, pflip) in enumerate(trials, 1):
        tag = f"{pol}_{prof}_{seed}" + ("_thermal" if therm else "")
        if pflip is not None:
            tag += f"_p{pflip}"
        out = f"{OUT}/{tag}.json"
        if os.path.exists(out):
            L(f"[{i}/{len(trials)}] skip {tag}"); continue
        cmd = [PY, SCRIPT, "--policy", pol, "--profile", prof, "--seed", str(seed),
               "--workdir", WD, "--out", out] + COMMON
        if prof == "markov":
            # argparse takes the last value, so these override COMMON's interval/comp-life
            cmd += ["--interval", MK_INTERVAL, "--comp-life", MK_COMPLIFE]
        if pflip is not None:
            cmd += ["--p-flip", str(pflip)]
        if therm:
            cmd += ["--thermal", "--setpoint", "80"]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
        L(f"[{i}/{len(trials)}] {tag} {int(time.time() - t)}s :: {line}")
    L(f"[campaign] DONE @ {time.strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
