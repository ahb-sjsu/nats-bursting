"""Compute-bound warm-pool scaling: aggregate MiniLM embedding throughput vs worker
count, workers round-robined across both GV100s. Unlike the I/O-bound warm-pool
result (throughput plateaus at concurrency/RTT, Little's law), a compute-bound AI
workload should scale with worker count until the GPUs saturate -- the "GPU cluster
doing real AI work" result. Uses the base venv (sentence-transformers). One point
per invocation (given --workers).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

EMBED = (
    "import os,sys,time\n"
    "os.environ['HF_HOME']='/archive/cache/huggingface'; os.environ['HF_HUB_OFFLINE']='1'\n"
    "os.environ['TOKENIZERS_PARALLELISM']='false'\n"
    "from sentence_transformers import SentenceTransformer\n"
    "m=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device='cuda')\n"
    "docs=['the quick brown fox jumps over the lazy dog']*{batch}\n"
    "m.encode(docs,batch_size=128,convert_to_numpy=True)  # warm\n"
    "t=time.time(); n=0\n"
    "for _ in range({iters}): m.encode(docs,batch_size=128,convert_to_numpy=True); n+={batch}\n"
    "open(sys.argv[1],'w').write('%d %f'%(n, time.time()-t))\n"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--gpus", default="0,1")
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--pybin", default="/home/claude/env/bin/python3")
    ap.add_argument("--workdir", default="/tmp/e9/scale")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.workdir, exist_ok=True)
    gpus = a.gpus.split(",")
    code = EMBED.format(batch=a.batch, iters=a.iters)
    procs, rfs = [], []
    t0 = time.time()
    for i in range(a.workers):
        rf = os.path.join(a.workdir, f"w{a.workers}_{i}.txt")
        rfs.append(rf)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpus[i % len(gpus)])
        procs.append(subprocess.Popen([a.pybin, "-c", code, rf], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait()
    wall = time.time() - t0
    total, max_dt = 0, 0.0
    for rf in rfs:
        try:
            n, dt = open(rf).read().split()
            total += int(n); max_dt = max(max_dt, float(dt))
        except Exception:
            pass
    # steady-state throughput = docs across workers / slowest worker's timed window
    thr = total / max_dt if max_dt else 0.0
    res = {"workers": a.workers, "gpus": len(gpus), "total_docs": total,
           "timed_window_s": round(max_dt, 2), "wall_s": round(wall, 2),
           "throughput_docs_s": round(thr, 1)}
    json.dump(res, open(a.out, "w"), indent=2)
    print(f"[scale] W={a.workers} ({len(gpus)} GPUs): {res['throughput_docs_s']} docs/s "
          f"({total} docs / {max_dt:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
