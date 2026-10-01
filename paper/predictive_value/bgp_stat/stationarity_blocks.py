"""Block-stationarity check (PROTOCOL-BGP-STATIONARITY.md (b)).
Per series: 3 contiguous blocks (index thirds for the single-run *_v2 series;
calendar thirds of the window for BGP, missing minutes excluded). Per block:
pi_hat, P(1|0), P(1|1); the v5 quantities via bgp_v5.domain (identical code
path, M=299, seeds 9000+s, series' own full lag grid); the v5c selection-aware
sel_L05 via bgp_v5c functions (repaired kk_max draws; grid every 2nd lag + the
block's D*; N_BOOT=2000; seed 0); certificate 2[(sel_L05)^+]^2 if detected.
Supplementary (not in the registered list, used only to apply the verdict
rules): the v5b fixed-D* lower bound L05 via bgp_v5b functions.
Homogeneity: Anderson-Goodman chi-square of equal lag-1 transition matrices
across the three blocks (sum over previous state of 3x2 Pearson chi-square, df=4).
Output: /archive/infocom_battery/bgp_stat/stationarity.json
"""
import json
import sys
import time

sys.path.insert(0, "/archive/infocom_battery/bgp_stat")
import numpy as np
from scipy.stats import chi2, chi2_contingency

import bgp_series
import bgp_v5 as V5
import bgp_v5b as V5B
import bgp_v5c as V5C
import calibrate_par as C

OUT = "/archive/infocom_battery/bgp_stat/stationarity.json"
PFLOOR = 1 / 300
FLOOR = 0.03


def blocks_of(title):
    if title == "BGP rrc06 updates":
        return [bgp_series.load_bgp(lo, hi) for lo, hi in ((0, 3360), (3360, 6720), (6720, 10080))]
    name = {"Seismic ANMO": "seismic_v2", "GOES X-ray flux": "xray_v2",
            "GOES magnetometer": "mag_v2", "GOES protons": "protons_v2"}[title]
    x = C.npy(name)[0]
    return [[b] for b in np.array_split(x, 3)]


def trans(S):
    T = np.zeros((2, 2))
    for x in S:
        a, b = x[:-1].astype(int), x[1:].astype(int)
        for i in (0, 1):
            for j in (0, 1):
                T[i, j] += np.sum((a == i) & (b == j))
    return T


def verdict(p, g, U2, LD, Lmax):
    det = p <= PFLOOR + 1e-12
    if det:
        if g < FLOOR:
            return "detected, below floor"
        if LD is not None and LD > FLOOR and Lmax > FLOOR:
            return "history adds"
        return "detected (exploratory)"
    return "equivalent" if U2 < FLOOR else "not established"


SERIES = [
    ("Seismic ANMO", "seismology", 1 / 60.0, C.flags(90)),
    ("GOES X-ray flux", "space weather", 1 / 60.0, C.flags(90)),
    ("GOES magnetometer", "space weather", 1 / 60.0, C.flags(90)),
    ("GOES protons", "space weather", 1 / 300.0, C.flags(40, shortstep=1)),
    ("BGP rrc06 updates", "internet routing", 1 / 60.0, C.flags(90)),
]


def main():
    res = []
    for title, phys, rate, lags in SERIES:
        blks = blocks_of(title)
        Ts, rows = [], []
        for bi, S in enumerate(blks):
            t0 = time.time()
            T = trans(S); Ts.append(T)
            allx = np.concatenate(S)
            d = V5.domain(f"{title} [block {bi + 1}/3]", phys, S, rate, lags)
            Dstar = d["D_star"]
            lags_c = sorted(set(list(d["lags"])[::2] + [Dstar]))
            diffs = V5C.paired_all_lags(S, lags_c)
            maxes = V5C.selection_aware_boot(diffs, block_of=lambda D: max(10, 2 * D))
            selL = float(np.percentile(maxes, 5))
            dv = V5B.paired_vs_exact(S, Dstar)
            LD = float(np.percentile(V5B.block_boot(dv, block=max(10, 2 * Dstar)), 5)) if dv else None
            det = d["p_mc"] <= PFLOOR + 1e-12
            row = dict(block=bi + 1, n_samples=int(len(allx)), n_runs=len(S),
                       pi_hat=float(allx.mean()),
                       P1_given0=float(T[0, 1] / T[0].sum()), P1_given1=float(T[1, 1] / T[1].sum()),
                       max_gain=d["max_gain"], p_mc=d["p_mc"], eps_over=d["eps_over"],
                       eps_under=d["eps_under"], U2=d["equiv_U_two_tail"], D_star=Dstar,
                       sel_L05=selL, sel_U95=float(np.percentile(maxes, 95)), n_sel_lags=len(lags_c),
                       L05_fixedDstar_v5b=LD, detected=bool(det),
                       certificate_nats=(float(2 * max(selL, 0) ** 2) if det else None),
                       verdict=verdict(d["p_mc"], d["max_gain"], d["equiv_U_two_tail"], LD, selL),
                       v5_full=d, seconds=round(time.time() - t0, 1))
            rows.append(row)
            print(f"  {title} b{bi + 1}: n={row['n_samples']} pi={row['pi_hat']:.3f} "
                  f"P10={row['P1_given0']:.3f} P11={row['P1_given1']:.3f} g={row['max_gain']:+.4f} "
                  f"p={row['p_mc']:.4f} U2={row['U2']:.4f} D*={Dstar} selL05={selL:+.4f} "
                  f"LD*={LD} -> {row['verdict']} ({row['seconds']}s)", flush=True)
            res_partial = res + [dict(title=title, blocks=rows)]
            json.dump(dict(series=res_partial), open(OUT, "w"), indent=1)
        stat, df = 0.0, 0
        for i in (0, 1):
            tab = np.array([T[i] for T in Ts])
            s, _, dfi, _ = chi2_contingency(tab, correction=False)
            stat += s; df += dfi
        hom = dict(chi2=float(stat), df=int(df), p=float(chi2.sf(stat, df)))
        out = dict(title=title, blocks=rows, homogeneity=hom)
        if title == "Seismic ANMO":
            fail = [r["block"] for r in rows if not r["sel_L05"] > FLOOR]
            out["reading"] = ("block-robust" if not fail else f"not block-robust; failing blocks {fail}")
        res.append(out)
        print(f"{title}: homogeneity chi2={stat:.2f} df={df} p={hom['p']:.3g} "
              f"{out.get('reading', '')}", flush=True)
        json.dump(dict(series=res), open(OUT, "w"), indent=1)
    print("STATIONARITY_DONE", flush=True)


if __name__ == "__main__":
    main()
