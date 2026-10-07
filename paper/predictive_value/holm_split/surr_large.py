"""Larger surrogate sets and the Holm detection rule (PROTOCOL-HOLM-SPLIT.md (1)).

Usage: surr_large.py main|blocks
  main   : the ten battery series (battery_v5.json + bgp_stat/bgp_v5.json)
  blocks : the fifteen calendar-block tests (bgp_stat/stationarity.json)
Statistic, surrogate generator and lag grids are those of battery_v5.py.
M = 4999, seeds 9000+s; the first 299 seeds are the original ones, and the
script checks that it reproduces the stored gain and the stored count.
CPU only, n_jobs=8. Output: /archive/infocom_battery/holm_split/surr_<family>.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from joblib import Parallel, delayed

import battery_v5 as V5
import boundary_map as B
import bgp_series
import calibrate_par as C

BAT = "/archive/infocom_battery"
M_NEW, M_OLD, ALPHA, NJOBS = 4999, 299, 0.05, 8


def states(title):
    if title == "Two-state Markov":
        return C.gen_markov(20000, 0.02, 1)
    if title == "i.i.d. null":
        return [np.random.default_rng(2).integers(0, 2, 20000).astype(np.int8)]
    if title == "LOCATA azimuth":
        return B.collect(B.load_azimuth)
    if title == "LOCATA VAD":
        return B.collect(B.load_vad)
    if title == "Sperm-whale codas":
        return C.load_whale()
    if title == "BGP rrc06 updates":
        return bgp_series.load_bgp()
    name = {"GOES X-ray flux": "xray_v2", "GOES magnetometer": "mag_v2",
            "GOES protons": "protons_v2", "Seismic ANMO": "seismic_v2"}[title]
    return C.npy(name)


def blocks_of(title):
    """Copied from bgp_stat/stationarity_blocks.py."""
    if title == "BGP rrc06 updates":
        return [bgp_series.load_bgp(lo, hi) for lo, hi in ((0, 3360), (3360, 6720), (6720, 10080))]
    name = {"Seismic ANMO": "seismic_v2", "GOES X-ray flux": "xray_v2",
            "GOES magnetometer": "mag_v2", "GOES protons": "protons_v2"}[title]
    x = C.npy(name)[0]
    return [[b] for b in np.array_split(x, 3)]


def tests(family):
    """(label, S, lags, stored max_gain, stored p) for every test in the family."""
    out = []
    if family == "main":
        doms = (json.load(open(f"{BAT}/battery_v5.json"))["domains"]
                + json.load(open(f"{BAT}/bgp_stat/bgp_v5.json"))["domains"])
        for d in doms:
            out.append((d["title"], lambda t=d["title"]: states(t), d["lags"], d["max_gain"], d["p_mc"]))
    else:
        st = json.load(open(f"{BAT}/bgp_stat/stationarity.json"))["series"]
        for s in st:
            for b in s["blocks"]:
                lab = f"{s['title']} [block {b['block']}/3]"
                out.append((lab, lambda t=s["title"], i=b["block"] - 1: blocks_of(t)[i],
                            b["v5_full"]["lags"], b["max_gain"], b["p_mc"]))
    return out


def holm(ps, alpha):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    m, rej, thr = len(ps), [False] * len(ps), [None] * len(ps)
    stopped = False
    for r, i in enumerate(order):
        thr[i] = alpha / (m - r)
        if not stopped and ps[i] <= thr[i]:
            rej[i] = True
        else:
            stopped = True
    return rej, thr


def main(family):
    out_path = f"{HERE}/surr_{family}.json"
    res = []
    for label, getS, lags, g_old, p_old in tests(family):
        t0 = time.time()
        S = getS()
        gain = np.array([V5.kfold_value(S, int(D), C.K)[0] - V5.exact_v1(S, int(D))[0] for D in lags])
        gmax = float(gain.max())
        errs = np.array(Parallel(n_jobs=NJOBS, prefer="processes")(
            delayed(V5.surrogate_err)(S, lags, 9000 + s) for s in range(M_NEW)))
        cnt_old = int(np.sum(errs[:M_OLD] >= gmax))
        cnt_new = int(np.sum(errs >= gmax))
        guard_gain = abs(gmax - g_old) < 1e-12
        guard_count = cnt_old == int(round(p_old * (M_OLD + 1) - 1))
        row = dict(test=label, max_gain=gmax, max_gain_stored=g_old,
                   p_old=p_old, count_first299=cnt_old, count=cnt_new,
                   p_new=float((1 + cnt_new) / (M_NEW + 1)),
                   guard_gain=bool(guard_gain), guard_count=bool(guard_count),
                   eps_over_M4999=float(np.percentile(errs, 95)),
                   eps_under_M4999=float(-np.percentile(errs, 5)),
                   U2_M4999=float(gmax - np.percentile(errs, 5)),
                   seconds=round(time.time() - t0, 1))
        np.save(f"{HERE}/errs_{family}_{len(res):02d}.npy", errs)
        res.append(row)
        print(f"{label:34s} g={gmax:+.4f} p_old={p_old:.4f} p_new={row['p_new']:.5f} "
              f"guards={guard_gain}/{guard_count} ({row['seconds']}s)", flush=True)
        json.dump(dict(family=family, M=M_NEW, alpha=ALPHA, tests=res), open(out_path, "w"), indent=1)
    valid = [r for r in res if r["guard_gain"] and r["guard_count"]]
    rej, thr = holm([r["p_new"] for r in valid], ALPHA)
    for r, j, t in zip(valid, rej, thr):
        r["holm_threshold"], r["holm_reject"] = t, bool(j)
    json.dump(dict(family=family, M=M_NEW, alpha=ALPHA, tests=res,
                   deviations=[r["test"] for r in res if r not in valid]),
              open(out_path, "w"), indent=1)
    print(f"HOLM {family}: rejected", [r["test"] for r in valid if r.get("holm_reject")], flush=True)
    print("SURR_LARGE_DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
