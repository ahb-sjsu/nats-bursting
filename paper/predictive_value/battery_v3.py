"""Battery v3 for the predictive-value paper: the exact law, the delayed-history
test, AND the predictive-information envelope, per domain.

Reuses the registered confirm protocol verbatim (/tmp/calibrate_par.py: block-CV
lookup predictor K=6, lag-1-transition-matched Markov surrogates, pooled r(D))
and adds the plug-in mutual information I(X_t; X_{t-D}) with the envelope
sqrt(I/2) (nats; Omega=1 for the 0/1 prediction objective).

CPU-only, n_jobs<=20 (thermal cap); does not touch the GPU step-1 job.
Output: /archive/infocom_battery/battery_v3.json
"""
import json
import sys
import time

sys.path.insert(0, "/tmp")
import numpy as np
from joblib import Parallel, delayed

import boundary_map as B
import calibrate_par as C

M_SURR = 60


def mi_nats(S, D):
    """Plug-in I(X_t; X_{t-D}) in nats, pairs pooled across runs (as r_full)."""
    cnt = np.zeros((2, 2))
    for x in S:
        if len(x) > D:
            a, b = x[:-D].astype(int), x[D:].astype(int)
            for i in (0, 1):
                for j in (0, 1):
                    cnt[i, j] += np.sum((a == i) & (b == j))
    n = cnt.sum()
    if n == 0:
        return 0.0, 0
    p = cnt / n
    px, py = p.sum(1, keepdims=True), p.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = p * np.log(p / (px * py))
    return float(np.nansum(t)), int(n)


def domain(title, phys, S, rate, lags):
    t0 = time.time()
    r = np.array([C.r_full(S, D) for D in lags])
    acc = np.array([C.kfold(S, D, C.K) for D in lags])  # value above chance
    gain = acc - 0.5 * r
    surr = np.array(Parallel(n_jobs=20, prefer="processes")(
        delayed(C.surrogate_gain)(S, lags, 9000 + s) for s in range(M_SURR)))
    lo, hi = np.percentile(surr, [2.5, 97.5], axis=0)
    p = float((surr.max(axis=1) >= gain.max()).mean())
    mi = [mi_nats(S, int(D)) for D in lags]
    I = np.array([m[0] for m in mi])
    env = np.sqrt(np.maximum(I, 0) / 2)
    strong = r > 0.05
    out = dict(
        title=title, physics=phys, rate=rate, lags=[int(x) for x in lags],
        r=r.tolist(), delta_hist=acc.tolist(), law=(0.5 * r).tolist(),
        gain=gain.tolist(), surr_lo=lo.tolist(), surr_hi=hi.tolist(), p=p,
        max_gain=float(gain.max()),
        I_nats=I.tolist(), n_pairs=[m[1] for m in mi], envelope=env.tolist(),
        max_env_violation=float(np.max(acc - env)),
        med_env_over_law=(float(np.median(env[strong] / (0.5 * r[strong])))
                          if strong.any() else None),
        seconds=round(time.time() - t0, 1),
    )
    print(f"{title:22s} maxgain={gain.max():+.3f} p={p:.3f} "
          f"maxenvviol={out['max_env_violation']:+.4f} "
          f"env/law={out['med_env_over_law']}", flush=True)
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
    json.dump({"M_surr": M_SURR, "K": C.K, "floor": C.FLOOR, "domains": res},
              open("/archive/infocom_battery/battery_v3.json", "w"), indent=1)
    print("BATTERY_V3_DONE", flush=True)


if __name__ == "__main__":
    main()
