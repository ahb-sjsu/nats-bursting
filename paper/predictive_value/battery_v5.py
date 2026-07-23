"""Battery v5 — the registered upgrade path (paper v0.6 protocol):
  (a) BOTH calibration tails saved: eps_over = q95(E), eps_under = -q05(E)
      from the surrogate error sample (v4 kept only the upper tail);
  (b) dependence-aware interval: moving-block bootstrap on held-out PAIRED
      loss differences d_t = correct(k=6 policy, t) - correct(k=1 policy, t),
      same CV folds both arms, blocks resampled within runs; one-sided 95%
      bounds on the class gain at the argmax lag D*.
Estimand note: the paired arm compares the registered k=6 lookup class to
the k=1 (single-sample lookup) class under identical CV; the k=1 CV value
approximates the exact plug-in V1 (both reported).
CPU-only, n_jobs<=20. Output: /archive/infocom_battery/battery_v5.json
"""
import json
import sys
import time

sys.path.insert(0, "/tmp")
import numpy as np
from joblib import Parallel, delayed

import boundary_map as B
import calibrate_par as C

M_SURR = 299
FLOOR = 0.03
N_BOOT = 2000


def lag_table(S, D):
    cnt = np.zeros((2, 2))
    for x in S:
        if len(x) > D:
            a, b = x[:-D].astype(int), x[D:].astype(int)
            for i in (0, 1):
                for j in (0, 1):
                    cnt[i, j] += np.sum((a == i) & (b == j))
    return cnt


def exact_v1(S, D):
    cnt = lag_table(S, D); n = cnt.sum()
    if n == 0:
        return 0.0, 0.5
    p = cnt / n
    w = p.sum(1); pi = p.sum(0)[1]
    v = sum(w[y] * max(p[y, 1] / w[y], 1 - p[y, 1] / w[y]) for y in (0, 1) if w[y] > 0)
    return float(v - max(pi, 1 - pi)), float(pi)


def eval_vec(x, pred, gm, D, k):
    """Per-position correctness vector of a lookup policy on one run."""
    out = []
    for t in range(D + k - 1, len(x)):
        key = tuple(int(x[t - D - j]) for j in range(k))
        out.append(1 if pred.get(key, gm) == int(x[t]) else 0)
    return np.array(out, dtype=np.int8)


def kfold_value(S, D, k, Kf=5, paired_with=None):
    """CV accuracy above majority; if paired_with=k2, also return per-run
    paired difference vectors (k-policy minus k2-policy, same folds)."""
    pi = exact_v1(S, D)[1]
    base = max(pi, 1 - pi)
    correct = tot = 0
    diffs = []
    for x in S:
        n = len(x)
        if n < Kf * (D + k + 5):
            continue
        b = [int(i * n / Kf) for i in range(Kf + 1)]
        folds = [x[b[i]:b[i + 1]] for i in range(Kf)]
        run_diffs = []
        for f in range(Kf):
            train = [folds[j] for j in range(Kf) if j != f]
            pred, gm = B.train_lookup(train, D, k)
            v1 = eval_vec(folds[f], pred, gm, D, k)
            correct += int(v1.sum()); tot += len(v1)
            if paired_with is not None:
                pred2, gm2 = B.train_lookup(train, D, paired_with)
                v2 = eval_vec(folds[f], pred2, gm2, D, paired_with)
                m = min(len(v1), len(v2))
                run_diffs.append(v1[-m:].astype(np.int16) - v2[-m:].astype(np.int16))
        if run_diffs:
            diffs.append(np.concatenate(run_diffs))
    acc = (correct / tot) if tot else base
    return acc - base, diffs


def block_bootstrap(diffs, block, n_boot, seed=0):
    """Moving-block bootstrap of the mean paired difference; blocks within runs."""
    rng = np.random.default_rng(seed)
    n_tot = sum(len(d) for d in diffs)
    if n_tot == 0:
        return None
    means = np.empty(n_boot)
    for bi in range(n_boot):
        s = 0.0
        for d in diffs:
            n = len(d)
            L = min(block, max(2, n // 3))
            k = max(1, int(np.ceil(n / L)))
            starts = rng.integers(0, max(1, n - L + 1), size=k)
            take = np.concatenate([d[s0:s0 + L] for s0 in starts])[:n]
            s += take.sum()
        means[bi] = s / n_tot
    return means


def surrogate_err(S, lags, seed):
    Ss = C.surrogate(S, seed)
    g = [kfold_value(Ss, int(D), C.K)[0] - exact_v1(Ss, int(D))[0] for D in lags]
    return float(np.max(g))


def domain(title, phys, S, rate, lags):
    t0 = time.time()
    v1s = [exact_v1(S, int(D)) for D in lags]
    v1 = np.array([v[0] for v in v1s]); pi = float(np.median([v[1] for v in v1s]))
    hist = np.array([kfold_value(S, int(D), C.K)[0] for D in lags])
    gain = hist - v1
    kstar = int(np.argmax(gain)); Dstar = int(lags[kstar])
    errs = np.array(Parallel(n_jobs=20, prefer="processes")(
        delayed(surrogate_err)(S, lags, 9000 + s) for s in range(M_SURR)))
    p = float((1 + np.sum(errs >= gain.max())) / (M_SURR + 1))
    eps_over = float(np.percentile(errs, 95))
    eps_under = float(-np.percentile(errs, 5))
    # paired dependence-aware interval at D*
    _, diffs = kfold_value(S, Dstar, C.K, paired_with=1)
    boots = block_bootstrap(diffs, block=max(10, 2 * Dstar), n_boot=N_BOOT)
    paired_mean = (float(np.mean(np.concatenate(diffs))) if diffs else None)
    out = dict(
        title=title, physics=phys, pi=pi, lags=[int(x) for x in lags],
        gain=gain.tolist(), max_gain=float(gain.max()), D_star=Dstar,
        p_mc=p, eps_over=eps_over, eps_under=eps_under,
        equiv_U_two_tail=float(gain.max() + eps_under),
        I_cond_LB_modelcal=float(2 * max(gain.max() - eps_over, 0) ** 2),
        paired_mean_at_Dstar=paired_mean,
        paired_L95=(float(np.percentile(boots, 5)) if boots is not None else None),
        paired_U95=(float(np.percentile(boots, 95)) if boots is not None else None),
        I_cond_LB_blockboot=(float(2 * max(np.percentile(boots, 5), 0) ** 2)
                             if boots is not None else None),
        block_len=max(10, 2 * Dstar), n_boot=N_BOOT,
        seconds=round(time.time() - t0, 1),
    )
    print(f"{title:20s} g={out['max_gain']:+.3f} p={p:.4f} "
          f"eps=({eps_over:.3f},{eps_under:.3f}) U2={out['equiv_U_two_tail']:.3f} "
          f"paired=[{out['paired_L95']},{out['paired_U95']}] "
          f"Icond(bb)={out['I_cond_LB_blockboot']}", flush=True)
    return out


def main():
    AZ = B.collect(B.load_azimuth); VAD = B.collect(B.load_vad); WH = C.load_whale()
    doms = [
        ("Two-state Markov", "ref", C.gen_markov(20000, 0.02, 1), 1.0, C.flags(130)),
        ("i.i.d. null", "control",
         [np.random.default_rng(2).integers(0, 2, 20000).astype(np.int8)],
         1.0, C.flags(130)),
        ("LOCATA azimuth", "acoustics", AZ, 120.0, C.flags(120)),
        ("LOCATA VAD", "acoustics", VAD, 120.0, C.flags(120)),
        ("Sperm-whale codas", "bioacoustics", WH, 1.0, C.flags(40, shortstep=1)),
        ("GOES X-ray flux", "space weather", C.npy("xray_v2"), 1 / 60.0, C.flags(90)),
        ("GOES magnetometer", "space weather", C.npy("mag_v2"), 1 / 60.0, C.flags(90)),
        ("GOES protons", "space weather", C.npy("protons_v2"), 1 / 300.0,
         C.flags(40, shortstep=1)),
        ("Seismic ANMO", "seismology", C.npy("seismic_v2"), 1 / 60.0, C.flags(90)),
    ]
    res = []
    for d in doms:
        try:
            res.append(domain(*d))
        except Exception as e:
            print(f"{d[0]}: SKIP ({type(e).__name__}: {e})", flush=True)
        json.dump({"M_surr": M_SURR, "floor": FLOOR, "n_boot": N_BOOT,
                   "domains": res},
                  open("/archive/infocom_battery/battery_v5.json", "w"), indent=1)
    print("BATTERY_V5_DONE", flush=True)


if __name__ == "__main__":
    main()
