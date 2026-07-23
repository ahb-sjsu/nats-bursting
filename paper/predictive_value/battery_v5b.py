"""v5b: VALID conservative pairing for the conditional-information certificate.
d_t = correct(k=6 CV policy, t) - correct(EXACT pooled-table single-sample
policy, t). The exact arm is fit in-sample on the full series (favours the
single-sample arm), so the block-bootstrap lower bound on mean(d) is a
conservative lower bound on Delta_W - Delta_Z --- the quantity Theorem
(incremental) converts into I(X;H|Z) >= 2 L^2. Runs at each domain's v5 D*.
"""
import json, sys, time
sys.path.insert(0, "/tmp")
import numpy as np
import boundary_map as B
import calibrate_par as C

V5 = json.load(open("/archive/infocom_battery/battery_v5.json"))
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

def paired_vs_exact(S, D, k=6, Kf=5):
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
            v6, v1 = [], []
            for t in range(D + k - 1, len(xf)):
                key = tuple(int(xf[t-D-j]) for j in range(k))
                v6.append(1 if pred.get(key, gm) == int(xf[t]) else 0)
                v1.append(1 if pol[int(xf[t-D])] == int(xf[t]) else 0)
            if v6:
                run.append(np.array(v6, np.int16) - np.array(v1, np.int16))
        if run:
            diffs.append(np.concatenate(run))
    return diffs

def block_boot(diffs, block, seed=0):
    rng = np.random.default_rng(seed)
    n_tot = sum(len(d) for d in diffs)
    means = np.empty(N_BOOT)
    for bi in range(N_BOOT):
        s = 0.0
        for d in diffs:
            n = len(d); L = min(block, max(2, n//3)); kk = max(1, int(np.ceil(n/L)))
            starts = rng.integers(0, max(1, n-L+1), size=kk)
            s += np.concatenate([d[s0:s0+L] for s0 in starts])[:n].sum()
        means[bi] = s / n_tot
    return means

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

out = []
for dom in V5["domains"]:
    S = states(dom["title"]); D = dom["D_star"]
    diffs = paired_vs_exact(S, D)
    if not diffs:
        print(dom["title"], "no data"); continue
    boots = block_boot(diffs, block=max(10, 2*D))
    L05, U95 = float(np.percentile(boots,5)), float(np.percentile(boots,95))
    mean = float(np.mean(np.concatenate(diffs)))
    icond = float(2 * max(L05, 0)**2)
    out.append(dict(title=dom["title"], D_star=D, mean=mean, L05=L05, U95=U95,
                    I_cond_LB_valid=icond))
    print(f'{dom["title"]:20s} D*={D:3d} mean={mean:+.4f} CI=[{L05:+.4f},{U95:+.4f}] I_cond>={icond:.4f}', flush=True)
json.dump(out, open("/archive/infocom_battery/battery_v5b.json","w"), indent=1)
print("V5B_DONE", flush=True)
