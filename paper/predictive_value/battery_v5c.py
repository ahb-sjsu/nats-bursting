"""v5c: SELECTION-AWARE dependence-aware lower bound (round-5 refinement).
Per domain: precompute paired diff series d_D(t) (k=6 CV policy vs pooled-EXACT
single-sample policy) at EVERY registered lag; per bootstrap replicate, resample
blocks (shared fractional starts across lags to preserve cross-lag dependence),
recompute every lag's mean, select the maximizing lag WITHIN the replicate, and
record that maximum. One-sided 95% lower bound = q05 of the max distribution.
Output: /archive/infocom_battery/battery_v5c.json
"""
import json, sys, time
sys.path.insert(0, "/tmp")
import numpy as np
import boundary_map as B
import calibrate_par as C

N_BOOT = 2000

def exact_policy(S, D):
    cnt = np.zeros((2,2))
    for x in S:
        if len(x) > D:
            a, b = x[:-D].astype(int), x[D:].astype(int)
            for i in (0,1):
                for j in (0,1):
                    cnt[i,j] += np.sum((a==i)&(b==j))
    p = cnt / max(cnt.sum(), 1)
    w = p.sum(1)
    return {y: (1 if (w[y] > 0 and p[y,1]/w[y] >= 0.5) else 0) for y in (0,1)}

def paired_all_lags(S, lags, k=6, Kf=5):
    """dict D -> list of per-run diff arrays."""
    out = {}
    for D in lags:
        D = int(D)
        pol = exact_policy(S, D)
        diffs = []
        for x in S:
            n = len(x)
            if n < Kf * (D + k + 5):
                continue
            b = [int(i*n/Kf) for i in range(Kf+1)]
            folds = [x[b[i]:b[i+1]] for i in range(Kf)]
            run = []
            for f in range(Kf):
                pred, gm = B.train_lookup([folds[j] for j in range(Kf) if j != f], D, k)
                xf = folds[f]
                v = []
                for t in range(D + k - 1, len(xf)):
                    key = tuple(int(xf[t-D-j]) for j in range(k))
                    c6 = 1 if pred.get(key, gm) == int(xf[t]) else 0
                    c1 = 1 if pol[int(xf[t-D])] == int(xf[t]) else 0
                    v.append(c6 - c1)
                if v: run.append(np.array(v, np.int16))
            if run: diffs.append(np.concatenate(run))
        if diffs: out[D] = diffs
    return out

def selection_aware_boot(diffs_by_lag, block_of, seed=0):
    rng = np.random.default_rng(seed)
    lags = sorted(diffs_by_lag)
    maxes = np.empty(N_BOOT)
    for bi in range(N_BOOT):
        fracs = rng.random(64)  # shared fractional block starts this replicate
        best = -1e9
        for D in lags:
            s = 0.0; n_tot = 0
            for d in diffs_by_lag[D]:
                n = len(d); L = min(block_of(D), max(2, n//3))
                kk = max(1, int(np.ceil(n/L)))
                starts = (fracs[:kk] * max(1, n - L + 1)).astype(int)
                s += np.concatenate([d[s0:s0+L] for s0 in starts])[:n].sum()
                n_tot += n
            m = s / n_tot if n_tot else -1e9
            if m > best: best = m
        maxes[bi] = best
    return maxes

def states(title):
    if title == "Two-state Markov": return C.gen_markov(20000, 0.02, 1)
    if title == "i.i.d. null":
        return [np.random.default_rng(2).integers(0,2,20000).astype(np.int8)]
    if title == "LOCATA azimuth": return B.collect(B.load_azimuth)
    if title == "LOCATA VAD": return B.collect(B.load_vad)
    if title == "Sperm-whale codas": return C.load_whale()
    if title == "GOES X-ray flux": return C.npy("xray_v2")
    if title == "GOES magnetometer": return C.npy("mag_v2")
    if title == "GOES protons": return C.npy("protons_v2")
    if title == "Seismic ANMO": return C.npy("seismic_v2")

V5 = json.load(open("/archive/infocom_battery/battery_v5.json"))
out = []
for dom in V5["domains"]:
    t0 = time.time()
    S = states(dom["title"])
    # thin the lag grid for tractability: every 2nd lag + always include D*
    lags = sorted(set(list(dom["lags"])[::2] + [dom["D_star"]]))
    diffs = paired_all_lags(S, lags)
    if not diffs:
        print(dom["title"], "no data", flush=True); continue
    obs_means = {D: float(np.mean(np.concatenate(v))) for D, v in diffs.items()}
    obs_max = max(obs_means.values())
    maxes = selection_aware_boot(diffs, block_of=lambda D: max(10, 2*D))
    L05 = float(np.percentile(maxes, 5))
    icond = float(2 * max(L05, 0)**2)
    out.append(dict(title=dom["title"], n_lags=len(lags), obs_max=obs_max,
                    sel_L05=L05, sel_U95=float(np.percentile(maxes, 95)),
                    I_cond_LB_selection_aware=icond,
                    seconds=round(time.time()-t0,1)))
    print(f'{dom["title"]:20s} lags={len(lags):2d} obsmax={obs_max:+.4f} '
          f'selL05={L05:+.4f} I_cond>={icond:.4f} ({out[-1]["seconds"]}s)', flush=True)
    json.dump(out, open("/archive/infocom_battery/battery_v5c.json","w"), indent=1)
print("V5C_DONE", flush=True)
