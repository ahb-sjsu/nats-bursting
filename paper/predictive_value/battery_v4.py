"""Battery v4 — the review-corrected protocol (supersedes v3).

Corrections implemented (paper Sec 'battery', v0.3):
  * static baseline = best MAJORITY policy max(pi, 1-pi), not 0.5;
  * the per-lag law value = EXACT empirical single-sample Bayes value V1 from
    the pooled 2x2 lag table (carries hinge dead zones; no symmetry assumed);
  * M = 299 surrogates; exact Monte-Carlo p = (1+#{>=obs})/(M+1);
  * per-domain estimator-error sample: each Markov surrogate's TRUE history
    gain is 0 and its own exact V1 is computable, so its estimated gain IS an
    error draw under matched dependence; eps_dom = 95th percentile;
  * equivalence bound U = gain_obs + eps_dom (claim 'no detectable excess'
    only if U < 0.03); witness LCB: I_window >= 2*((Delta_hat-eps_dom)^+)^2;
  * report pi_hat, pooled N, and both envelope columns.

CPU-only, n_jobs<=20 (thermal cap). Output:
/archive/infocom_battery/battery_v4.json
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


def lag_table(S, D):
    cnt = np.zeros((2, 2))
    for x in S:
        if len(x) > D:
            a, b = x[:-D].astype(int), x[D:].astype(int)
            for i in (0, 1):
                for j in (0, 1):
                    cnt[i, j] += np.sum((a == i) & (b == j))
    return cnt


def exact_v1_and_I(S, D):
    """Exact empirical single-sample Bayes value above majority, plug-in I (nats)."""
    cnt = lag_table(S, D)
    n = cnt.sum()
    if n == 0:
        return 0.0, 0.0, 0.5, 0
    p = cnt / n
    w_y = p.sum(1)                      # P(X_{t-D}=y)
    pi = p.sum(0)[1]                    # P(X_t=1)
    v_static = max(pi, 1 - pi)
    v_obs = sum(
        w_y[y] * max(p[y, 1] / w_y[y], 1 - p[y, 1] / w_y[y])
        for y in (0, 1) if w_y[y] > 0
    )
    px, py = p.sum(1, keepdims=True), p.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = p * np.log(p / (px * py))
    return float(v_obs - v_static), float(np.nansum(t)), float(pi), int(n)


def hist_value(S, D, pi):
    """History-policy accuracy above the majority baseline (blocked CV)."""
    acc_over_half = C.kfold(S, D, C.K)  # accuracy - 0.5
    return acc_over_half + 0.5 - max(pi, 1 - pi)


def domain_gains(S, lags):
    """Per-lag (hist value, exact V1, I, pi, N); gain = hist - V1."""
    rows = []
    for D in lags:
        v1, I, pi, n = exact_v1_and_I(S, int(D))
        dh = hist_value(S, int(D), pi)
        rows.append((dh, v1, I, pi, n))
    return rows


def surrogate_error(S, lags, seed):
    """One Markov surrogate's estimated max gain (true gain = 0): an error draw."""
    Ss = C.surrogate(S, seed)
    g = [hist_value(Ss, int(D), exact_v1_and_I(Ss, int(D))[2])
         - exact_v1_and_I(Ss, int(D))[0] for D in lags]
    return float(np.max(g))


def domain(title, phys, S, rate, lags):
    t0 = time.time()
    rows = domain_gains(S, lags)
    dh = np.array([r[0] for r in rows])
    v1 = np.array([r[1] for r in rows])
    I = np.array([r[2] for r in rows])
    pi = float(np.median([r[3] for r in rows]))
    npairs = int(np.min([r[4] for r in rows]))
    gain = dh - v1
    gmax = float(gain.max())
    errs = np.array(Parallel(n_jobs=20, prefer="processes")(
        delayed(surrogate_error)(S, lags, 9000 + s) for s in range(M_SURR)))
    p = float((1 + np.sum(errs >= gmax)) / (M_SURR + 1))
    eps = float(np.percentile(errs, 95))
    env = np.sqrt(np.maximum(I, 0) / 2)
    r_pool = np.array([C.r_full(S, int(D)) for D in lags])
    strong = np.abs(r_pool) > 0.05
    dh_max = float(dh.max())
    out = dict(
        title=title, physics=phys, rate=rate, lags=[int(x) for x in lags],
        pi=pi, n_pairs_min=npairs,
        hist=dh.tolist(), v1_exact=v1.tolist(), gain=gain.tolist(),
        I_nats=I.tolist(), envelope=env.tolist(), r=r_pool.tolist(),
        max_gain=gmax, p_mc=p, eps_dom=eps,
        equiv_U=gmax + eps,
        no_detectable_excess=bool((gmax + eps) < FLOOR),
        max_env_excess=float(np.max(dh - env)),
        env_excess_certified=bool(np.max(dh - env) > eps),
        I_window_LCB=float(2 * max(dh_max - eps, 0) ** 2),
        med_env_over_v1=(float(np.median(env[strong] / np.maximum(v1[strong], 1e-9)))
                         if strong.any() else None),
        seconds=round(time.time() - t0, 1),
    )
    print(f"{title:20s} pi={pi:.3f} gmax={gmax:+.3f} p={p:.4f} eps={eps:.3f} "
          f"U={out['equiv_U']:.3f} envexc={out['max_env_excess']:+.3f} "
          f"I_LCB={out['I_window_LCB']:.4f}", flush=True)
    return out


def main():
    AZ = B.collect(B.load_azimuth)
    VAD = B.collect(B.load_vad)
    WH = C.load_whale()
    doms = [
        ("Two-state Markov", "synthetic ref",
         C.gen_markov(20000, 0.02, 1), 1.0, C.flags(130)),
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
        json.dump({"M_surr": M_SURR, "K": C.K, "floor": FLOOR, "domains": res},
                  open("/archive/infocom_battery/battery_v4.json", "w"), indent=1)
    print("BATTERY_V4_DONE", flush=True)


if __name__ == "__main__":
    main()
