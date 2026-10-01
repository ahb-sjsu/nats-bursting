"""Registered BGP binary series (PROTOCOL-BGP-STATIONARITY.md (a)).
X_t = 1 if per-minute A+W element count > median over observed minutes (ties 0).
Missing minutes excluded; series = list of int8 runs of contiguous observed minutes."""
import numpy as np

D = "/archive/infocom_battery/bgp_stat"


def full_state():
    cnt = np.load(f"{D}/bgp_counts_per_minute.npy")
    obs = np.load(f"{D}/bgp_observed_mask.npy")
    med = float(np.median(cnt[obs]))
    x = (cnt > med).astype(np.int8)
    return x, obs, med, cnt


def runs(x, obs, lo=0, hi=None):
    hi = len(x) if hi is None else hi
    out, cur = [], []
    for t in range(lo, hi):
        if obs[t]:
            cur.append(x[t])
        elif cur:
            out.append(np.array(cur, np.int8)); cur = []
    if cur:
        out.append(np.array(cur, np.int8))
    return out


def load_bgp(lo=0, hi=None):
    x, obs, _, _ = full_state()
    return runs(x, obs, lo, hi)
