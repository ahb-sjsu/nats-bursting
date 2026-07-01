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
os.makedirs(OUT, exist_ok=True)
os.makedirs(WD, exist_ok=True)

POLICIES = ["naive", "static", "aimd"]
PROFILES = ["square", "poisson"]
SEEDS = [42, 43, 44, 45]
COMMON = ["--burst", "16", "--work", "1000", "--matmul", "4096",
          "--comp-life", "25", "--tau", "25", "--interval", "1",
          "--rate", "0.06", "--gpus", "1,0"]

trials = [(p, pr, s, False) for p, pr, s in itertools.product(POLICIES, PROFILES, SEEDS)]
trials += [("aimd", "square", s, True) for s in (42, 43)]     # thermal demo (H4)
trials += [("naive", "square", s, True) for s in (42,)]       # thermal under naive too
random.Random(2027).shuffle(trials)                            # interleaved order

logf = open("/tmp/e9/campaign.log", "a")


def L(m: str) -> None:
    logf.write(m + "\n"); logf.flush()
    print(m, flush=True)


L(f"[campaign] {len(trials)} trials @ {time.strftime('%H:%M:%S')}")
for i, (pol, prof, seed, therm) in enumerate(trials, 1):
    tag = f"{pol}_{prof}_{seed}" + ("_thermal" if therm else "")
    out = f"{OUT}/{tag}.json"
    if os.path.exists(out):
        L(f"[{i}/{len(trials)}] skip {tag}"); continue
    cmd = [PY, SCRIPT, "--policy", pol, "--profile", prof, "--seed", str(seed),
           "--workdir", WD, "--out", out] + COMMON
    if therm:
        cmd += ["--thermal", "--setpoint", "80"]
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    line = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
    L(f"[{i}/{len(trials)}] {tag} {int(time.time() - t)}s :: {line}")
L(f"[campaign] DONE @ {time.strftime('%H:%M:%S')}")
