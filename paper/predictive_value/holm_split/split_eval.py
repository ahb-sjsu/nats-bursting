"""Selection/evaluation split (PROTOCOL-HOLM-SPLIT.md (2)).

Single-run series: 4 equal contiguous chunks, chunks 0,2 select and 1,3
evaluate. Multi-run series: whole runs alternate (even index selects).
Selection: argmax over the v5 lag grid of the CV gain over the exact
single-sample value (battery_v5.py), on the selection set only; the k=6
lookup is then trained on the whole selection set at D*_sel.
Evaluation: d_t = correct(k=6 table) - correct(exact single-sample policy fit
in-sample on the evaluation set) at the frozen D*_sel; one-sided 95%
moving-block bootstrap, blocks within chunks/runs, block max(10, 2 D*),
N_BOOT=2000, seed 0 (battery_v5b.py functions, copied).
Output: /archive/infocom_battery/holm_split/split.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np

import battery_v5 as V5
import boundary_map as B
import calibrate_par as C
from surr_large import states

BAT = "/archive/infocom_battery"
K, N_BOOT, FLOOR = 6, 2000, 0.03


def exact_policy(S, D):
    """Copied from battery_v5b.py."""
    cnt = np.zeros((2, 2))
    for x in S:
        if len(x) > D:
            a, b = x[:-D].astype(int), x[D:].astype(int)
            for i in (0, 1):
                for j in (0, 1):
                    cnt[i, j] += np.sum((a == i) & (b == j))
    p = cnt / max(cnt.sum(), 1)
    w = p.sum(1)
    return {y: (1 if (w[y] > 0 and p[y, 1] / w[y] >= 0.5) else 0) for y in (0, 1)}


def block_boot(diffs, block, seed=0):
    """Copied from battery_v5b.py."""
    rng = np.random.default_rng(seed)
    n_tot = sum(len(d) for d in diffs)
    means = np.empty(N_BOOT)
    for bi in range(N_BOOT):
        s = 0.0
        for d in diffs:
            n = len(d); L = min(block, max(2, n // 3)); kk = max(1, int(np.ceil(n / L)))
            starts = rng.integers(0, max(1, n - L + 1), size=kk)
            s += np.concatenate([d[s0:s0 + L] for s0 in starts])[:n].sum()
        means[bi] = s / n_tot
    return means


def split(S):
    if len(S) == 1:
        ch = np.array_split(S[0], 4)
        return [ch[0], ch[2]], [ch[1], ch[3]], "chunks"
    return [x for i, x in enumerate(S) if i % 2 == 0], [x for i, x in enumerate(S) if i % 2 == 1], "runs"


def main():
    doms = (json.load(open(f"{BAT}/battery_v5.json"))["domains"]
            + json.load(open(f"{BAT}/bgp_stat/bgp_v5.json"))["domains"])
    res = []
    for d in doms:
        title, lags = d["title"], [int(D) for D in d["lags"]]
        sel, ev, how = split(states(title))
        gain = [V5.kfold_value(sel, D, K)[0] - V5.exact_v1(sel, D)[0] for D in lags]
        Dsel = lags[int(np.argmax(gain))]
        pred, gm = B.train_lookup(sel, Dsel, K)
        pol = exact_policy(ev, Dsel)
        diffs = []
        for x in ev:
            v6, v1 = [], []
            for t in range(Dsel + K - 1, len(x)):
                key = tuple(int(x[t - Dsel - j]) for j in range(K))
                v6.append(1 if pred.get(key, gm) == int(x[t]) else 0)
                v1.append(1 if pol[int(x[t - Dsel])] == int(x[t]) else 0)
            if v6:
                diffs.append(np.array(v6, np.int16) - np.array(v1, np.int16))
        boots = block_boot(diffs, block=max(10, 2 * Dsel))
        L = float(np.percentile(boots, 5))
        row = dict(title=title, split=how, n_sel=int(sum(len(x) for x in sel)),
                   n_eval=int(sum(len(x) for x in ev)), D_star_full=d["D_star"],
                   D_star_sel=Dsel, sel_max_gain=float(max(gain)),
                   eval_mean=float(np.mean(np.concatenate(diffs))), L_split=L,
                   U95_split=float(np.percentile(boots, 95)),
                   certificate_nats=float(2 * max(L, 0) ** 2), clears_floor=bool(L > FLOOR))
        res.append(row)
        print(f"{title:20s} {how:6s} D*full={d['D_star']:3d} D*sel={Dsel:3d} "
              f"mean={row['eval_mean']:+.4f} L={L:+.4f} cert={row['certificate_nats']:.4f}", flush=True)
        json.dump(dict(n_boot=N_BOOT, floor=FLOOR, series=res), open(f"{HERE}/split.json", "w"), indent=1)
    print("SPLIT_DONE", flush=True)


if __name__ == "__main__":
    main()
