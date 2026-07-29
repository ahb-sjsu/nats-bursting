"""E9-F: live matched-mismatch frontier campaign (run ON Atlas under
run_frontier_suspend.sh).

Fills the gap named in the paper's threats-to-validity: Table 1 compares the
feedback branch with ONE static operating point at unequal rho. This campaign
traces both curves on the same rig and days so goodput can be compared at
common mismatch:

  * static (record-independent) trickle:  --rate sweep -> (rho, g) curve
  * AIMD feedback branch:                 (alpha, beta) sweep -> (rho, g) curve

Square contention only (the regime where the paper claims value), parameters
identical to the published Table-1 cells: --burst 16 --work 1000 --matmul 4096
--tau 25 --comp-life 25 --interval 1 --gpus 1,0, seeds 42-45. The published
static (rate 0.06) and aimd (1, 0.5) cells are re-run inside this campaign so
every frontier point shares one rig session.

Randomized interleaved order, idempotent (skips existing JSONs), progress to
/tmp/e9/frontier.log. Analyzer: e9_frontier_analyze.py.
"""

from __future__ import annotations

import itertools
import os
import random
import subprocess
import time

PY = "/home/claude/env/bin/python3"
SCRIPT = "/home/claude/e9/e9_contended.py"
OUT = "/tmp/e9/frontier"
WD = "/tmp/e9/wd"

GPUS = os.environ.get("E9_GPUS", "1,0")
SEEDS = [42, 43, 44, 45]

# static trickle rates bracketing the published 0.06 (rho 0.11) up toward the
# naive corner; the frontier needs coverage of rho ~0.05-0.65
STATIC_RATES = [0.03, 0.05, 0.06, 0.08, 0.12, 0.18, 0.28]

# AIMD (alpha, beta): (1, 0.5) is the published cell; the others move rho
AIMD_PARAMS = [(1, 0.25), (1, 0.5), (1, 0.75), (2, 0.5), (3, 0.35)]

COMMON = ["--profile", "square", "--burst", "16", "--work", "1000",
          "--matmul", "4096", "--comp-life", "25", "--tau", "25",
          "--interval", "1", "--gpus", GPUS]

trials = [("static", r, None, s) for r, s in itertools.product(STATIC_RATES, SEEDS)]
trials += [("aimd", None, ab, s) for ab, s in itertools.product(AIMD_PARAMS, SEEDS)]


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(WD, exist_ok=True)
    random.Random(20260729).shuffle(trials)
    logf = open("/tmp/e9/frontier.log", "a")

    def L(m):
        logf.write(m + "\n"); logf.flush()
        print(m, flush=True)

    L(f"[frontier] {len(trials)} trials @ {time.strftime('%H:%M:%S')}")
    for i, (pol, rate, ab, seed) in enumerate(trials, 1):
        if pol == "static":
            tag = f"static_r{rate}_{seed}"
            extra = ["--rate", str(rate)]
        else:
            a_, b_ = ab
            tag = f"aimd_a{a_}b{b_}_{seed}"
            extra = ["--alpha", str(a_), "--beta", str(b_)]
        out = f"{OUT}/{tag}.json"
        if os.path.exists(out):
            L(f"[{i}/{len(trials)}] skip {tag}"); continue
        cmd = [PY, SCRIPT, "--policy", pol, "--seed", str(seed),
               "--workdir", WD, "--out", out] + COMMON + extra
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
        L(f"[{i}/{len(trials)}] {tag} {int(time.time() - t)}s :: {line}")
    L(f"[frontier] DONE @ {time.strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
