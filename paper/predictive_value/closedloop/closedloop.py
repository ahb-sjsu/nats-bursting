"""Registered closed-loop queue experiment (PROTOCOL-CLOSEDLOOP.md, commit 9d10b18).

Bottleneck queue K=20; reward w*(1-2X/K) (Omega=2); arrivals: own packet then
cross packet (p=0.3), each dropped if full; departure p=0.5 if nonempty.
Delay D; information (X_{t-D}, w_{t-D..t-1}).  Policies O / F1 / F2 grid-searched
on seeds 1-2, evaluated on held-out seeds 3-4.
"""
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[v] = "1"
import json, time, sys
import numpy as np
from joblib import Parallel, delayed

K = 20
LC, MU = 0.3, 0.5
OMEGA = 2.0
DS = [0, 1, 2, 4, 8, 16, 32, 64]
SEEDS = [20261001, 20261002, 20261003, 20261004]
BURN, MEAS = 10_000, 200_000
NBLK = 20
BLK = MEAS // NBLK
BOOT, BOOT_SEED = 2000, 20261005
P_GRID = np.round(np.arange(101) * 0.01, 2)
T1_GRID = np.arange(K + 2).astype(float)
T2_GRID = np.arange(85) * 0.25
R_OF_X = 1.0 - 2.0 * np.arange(K + 1) / K


def streams(seed):
    rng = np.random.default_rng(seed)
    n = BURN + MEAS
    return rng.random(n), rng.random(n), rng.random(n)


def simulate(D, seed, kinds, params, record=False):
    """kinds: 0=O, 1=F1, 2=F2.  Returns per-block reward sums (P, NBLK) and,
    if record, measured trajectories of (X_{t-D}, A_t, X_t) as int16 (T, P)."""
    kinds = np.asarray(kinds); params = np.asarray(params, float)
    P = len(kinds)
    isO, isF1, isF2 = kinds == 0, kinds == 1, kinds == 2
    Uo, Uc, Ud = streams(seed)
    cross = Uc < LC
    dep = Ud < MU
    X = np.zeros(P, np.int64)
    Xbuf = np.zeros((D + 1, P), np.int64)
    wbuf = np.zeros((max(D, 1), P), np.int64)
    A = np.zeros(P, np.int64)
    blk = np.zeros((P, NBLK))
    drift = D * (LC - MU)
    if record:
        tr = np.zeros((3, MEAS, P), np.int16)
    for t in range(BURN + MEAS):
        Xbuf[t % (D + 1)] = X
        xd = Xbuf[(t - D) % (D + 1)]          # X_{t-D} (0 before the start)
        xhat = np.clip(xd + A + drift, 0, K)
        w = np.where(isO, Uo[t] < params,
                     np.where(isF1, xd < params, xhat < params)).astype(np.int64)
        if t >= BURN:
            m = t - BURN
            blk[:, m // BLK] += w * R_OF_X[X]
            if record:
                tr[0, m] = xd; tr[1, m] = A; tr[2, m] = X
        if D > 0:
            j = t % D
            A += w - wbuf[j]
            wbuf[j] = w
        X = np.minimum(X + w, K)
        if cross[t]:
            X = np.minimum(X + 1, K)
        if dep[t]:
            X = X - (X > 0)
    return blk, (tr if record else None)


def phase1(D, seed):
    kinds = [0] * len(P_GRID) + [1] * len(T1_GRID) + [2] * len(T2_GRID)
    params = list(P_GRID) + list(T1_GRID) + list(T2_GRID)
    t0 = time.time()
    blk, _ = simulate(D, seed, kinds, params)
    print(f"phase1 D={D} seed={seed} {time.time()-t0:.1f}s", flush=True)
    return D, seed, blk.sum(1) / MEAS


def phase2(D, seed, sel):
    t0 = time.time()
    blk, tr = simulate(D, seed, [0, 1, 2], [sel["O"], sel["F1"], sel["F2"]], record=True)
    nS = (K + 1) * (D + 1)
    counts = {}
    for i, name in ((1, "F1"), (2, "F2")):
        S = tr[0, :, i].astype(np.int64) * (D + 1) + tr[1, :, i]
        x = tr[2, :, i].astype(np.int64)
        b = np.arange(MEAS) // BLK
        c = np.bincount((b * nS + S) * (K + 1) + x, minlength=NBLK * nS * (K + 1))
        counts[name] = c.reshape(NBLK, nS, K + 1)
    print(f"phase2 D={D} seed={seed} {time.time()-t0:.1f}s", flush=True)
    return D, seed, blk, counts


def delta_of(N):
    n = N.sum()
    m = N @ R_OF_X
    return np.maximum(0, m).sum() / n - max(0.0, m.sum() / n)


def mi_of(N):
    n = N.sum()
    ps = N.sum(1, keepdims=True) / n
    px = N.sum(0, keepdims=True) / n
    p = N / n
    nz = p > 0
    return float((p[nz] * np.log(p[nz] / (ps @ px)[nz])).sum())


def main(out):
    t0 = time.time()
    r1 = Parallel(n_jobs=4)(delayed(phase1)(D, s) for D in DS for s in SEEDS[:2])
    nO, n1 = len(P_GRID), len(T1_GRID)
    sel, selvals = {}, {}
    for D in DS:
        v = np.mean([r[2] for r in r1 if r[0] == D], axis=0)
        vO, v1, v2 = v[:nO], v[nO:nO + n1], v[nO + n1:]
        iO, i1, i2 = int(np.argmax(vO)), int(np.argmax(v1)), int(np.argmax(v2))  # first max = smallest param
        sel[D] = {"O": float(P_GRID[iO]), "F1": float(T1_GRID[i1]), "F2": float(T2_GRID[i2])}
        selvals[D] = {"O": float(vO[iO]), "F1": float(v1[i1]), "F2": float(v2[i2])}
        print(f"selected D={D}: {sel[D]} sel-seed values {selvals[D]}", flush=True)
    r2 = Parallel(n_jobs=4)(delayed(phase2)(D, s, sel[D]) for D in DS for s in SEEDS[2:])
    rng = np.random.default_rng(BOOT_SEED)
    res = []
    for D in DS:
        rr = sorted([r for r in r2 if r[0] == D], key=lambda r: r[1])
        blk = np.concatenate([r[2] for r in rr], axis=1) / BLK      # (3, 40) per-block mean reward
        V = blk.mean(1)
        fb = "F1" if V[1] >= V[2] else "F2"
        ifb = 1 if fb == "F1" else 2
        cnt = np.concatenate([r[3][fb] for r in rr], axis=0)        # (40, nS, K+1)
        N = cnt.sum(0).astype(float)
        I = mi_of(N)
        env = OMEGA * np.sqrt(I / 2)
        Dl = float(delta_of(N))
        g = float(V[ifb] - V[0])
        # bootstrap over 40 blocks
        idx = rng.integers(0, 2 * NBLK, (BOOT, 2 * NBLK))
        W = np.zeros((BOOT, 2 * NBLK))
        np.add.at(W, (np.repeat(np.arange(BOOT), 2 * NBLK), idx.ravel()), 1)
        dblk = blk[ifb] - blk[0]
        gb = W @ dblk / (2 * NBLK)
        mblk = cnt.astype(float) @ R_OF_X                           # (40, nS)
        nblk = cnt.sum((1, 2)).astype(float)
        Mb = W @ mblk
        nb = W @ nblk
        Db = np.maximum(0, Mb).sum(1) / nb - np.maximum(0, Mb.sum(1) / nb)
        row = {
            "D": D,
            "selected_params": sel[D],
            "selection_seed_values": selvals[D],
            "heldout_values": {"O": float(V[0]), "F1": float(V[1]), "F2": float(V[2])},
            "best_feedback": fb,
            "g_dyn": g, "g_dyn_ci95": [float(np.percentile(gb, 2.5)), float(np.percentile(gb, 97.5))],
            "I_nats_plugin": I, "envelope": float(env),
            "Delta": Dl, "Delta_ci95": [float(np.percentile(Db, 2.5)), float(np.percentile(Db, 97.5))],
            "reading_A_pass": bool(Dl <= env + 1e-12),
            "steering_share": (1 - Dl / g) if g > 0 else None,
            "n_S_cells_occupied": int((N.sum(1) > 0).sum()),
        }
        res.append(row)
        print(json.dumps(row), flush=True)
    meta = {"protocol": "paper/predictive_value/PROTOCOL-CLOSEDLOOP.md @ 9d10b18",
            "K": K, "lambda_c": LC, "mu": MU, "Omega": OMEGA, "seeds": SEEDS,
            "burn": BURN, "measured": MEAS, "blocks_per_seed": NBLK, "bootstrap": BOOT,
            "bootstrap_seed": BOOT_SEED, "runtime_s": time.time() - t0}
    json.dump({"meta": meta, "results": res}, open(out, "w"), indent=1)
    print("DONE", time.time() - t0, flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "closedloop.json")
