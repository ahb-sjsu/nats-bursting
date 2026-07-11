#!/usr/bin/env python3
r"""
Validate the INFOCOM feedback-usefulness law at the *controller* level.

Theory (infocom_aoi_model.tex, Thm 1 / Prop layer-cake): under age-D capacity
sensing, the goodput advantage of ANY closed-loop admission controller over the
best static budget, at matched over-admission, is

        Delta(D) = 1/2 * r(D),   r(D) = corr(a_t, a_{t-D})  =  (1-2p)^D

for a symmetric two-state capacity a_t in {A_lo, A_hi} with per-epoch flip prob p
and coherence time tau_c = -1/ln(1-2p). This harness simulates the actual window
controllers on that process and checks:

  (1) the delayed-threshold (Bayes-optimal) controller sits on the predicted line;
  (2) practical AIMD approaches it when tau_c >> D and degrades when tau_c <~ D;
  (3) a regime-adaptive controller (estimate r_hat online, switch AIMD<->static)
      tracks the upper envelope -- never worse than static, near-optimal throughout;
  (4) sweeping D, all curves collapse onto 1/2 * e^{-D/tau_c} vs D/tau_c.

This is a MODEL-level validation of the controllers (no cluster). The real-cluster
counterpart sweeps `contention.py --profile markov --p-flip ...` against run.py and
lands a few in-situ points on the same axes. NumPy only.

    python tau_sweep.py                 # sweep + figure
    python tau_sweep.py --T 200000      # tighter Monte-Carlo
"""
from __future__ import annotations

import argparse
import json
import math
import os

import numpy as np

A_LO, A_HI = 1.0, 2.0          # C=2 contended pair: a=2 free, a=1 contended
K, W_MIN = 2.0, 1.0            # guest pod cap / floor
ALPHA, BETA = 0.5, 0.5        # AIMD additive step / back-off factor


def markov_capacity(T: int, p: float, rng: np.random.Generator) -> np.ndarray:
    """Symmetric two-state {A_LO,A_HI} chain, per-epoch flip prob p (P[hi]=1/2)."""
    flips = rng.random(T) < p
    s = np.empty(T, dtype=bool)
    s[0] = rng.random() < 0.5
    cur = s[0]
    for t in range(1, T):          # sequential: state depends on previous
        if flips[t]:
            cur = not cur
        s[t] = cur
    return np.where(s, A_HI, A_LO)


def metrics(w: np.ndarray, a: np.ndarray) -> tuple[float, float]:
    """(over-admission fraction rho = P[w>a], goodput = E[min(w,a)])."""
    return float(np.mean(w > a + 1e-9)), float(np.mean(np.minimum(w, a)))


def static_goodput_at(rho: float) -> float:
    """Best static (obs-oblivious) goodput at over-admission rho, C=2 symmetric.
    Frontier is the mix of w=1 (rho=0,g=1) and w=2 (rho=1/2,g=3/2): g = 1 + rho."""
    return 1.0 + rho


def run_aimd(a: np.ndarray, D: int) -> np.ndarray:
    """AIMD window with detection delay D: signal s_t = 1[w_{t-D} > a_{t-D}]."""
    T = len(a)
    w = np.empty(T)
    w[0] = W_MIN
    for t in range(1, T):
        s = (t - 1 - D >= 0) and (w[t - 1 - D] > a[t - 1 - D] + 1e-9)
        w[t] = max(W_MIN, math.ceil(BETA * w[t - 1] * 2) / 2) if s \
            else min(w[t - 1] + ALPHA, K)
    return w


def run_threshold(a: np.ndarray, D: int) -> np.ndarray:
    """Bayes-optimal age-D policy: window = delayed capacity reading w_t = a_{t-D}."""
    w = np.full(len(a), W_MIN)
    if D < len(a):
        w[D:] = a[:len(a) - D]
    return w


def run_adaptive(a: np.ndarray, D: int, gamma: float = 0.15) -> np.ndarray:
    """Regime-adaptive: online r_hat=(1-2*p_hat)^D from the delayed-obs flip rate;
    run AIMD when r_hat>gamma (trackable), else fall back to safe static w=W_MIN."""
    T = len(a)
    w = np.empty(T)
    w[0] = W_MIN
    obs_hi = int(a[0] == A_HI)
    flips = 0
    seen = 1
    aimd_w = W_MIN
    for t in range(1, T):
        # update online flip-rate estimate from the age-D observation stream
        if t - D >= 1:
            prev = a[t - D - 1] == A_HI
            curr = a[t - D] == A_HI
            flips += int(prev != curr)
            seen += 1
        p_hat = flips / max(1, seen)
        r_hat = (1 - 2 * min(p_hat, 0.5)) ** D
        # advance an AIMD shadow window regardless (so a switch is warm)
        s = (t - 1 - D >= 0) and (aimd_w > a[t - 1 - D] + 1e-9)
        aimd_w = max(W_MIN, math.ceil(BETA * aimd_w * 2) / 2) if s \
            else min(aimd_w + ALPHA, K)
        w[t] = aimd_w if r_hat > gamma else W_MIN
    return w


def advantage(w: np.ndarray, a: np.ndarray) -> float:
    """Goodput gain over the best static at the controller's own over-admission."""
    rho, g = metrics(w, a)
    return g - static_goodput_at(rho)


def tau_c_of(p: float) -> float:
    return float("inf") if p <= 0 else -1.0 / math.log(1 - 2 * min(p, 0.4999))


def predicted(D: int, p: float) -> float:
    return 0.5 * (1 - 2 * min(p, 0.5)) ** D


def sweep_p(D: int, ps, T: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for p in ps:
        a = markov_capacity(T, p, rng)
        row = {"p": p, "tau_c": tau_c_of(p), "D": D, "predicted": predicted(D, p)}
        for name, w in (("threshold", run_threshold(a, D)),
                        ("aimd", run_aimd(a, D)),
                        ("adaptive", run_adaptive(a, D))):
            rho, g = metrics(w, a)
            row[name] = {"rho": round(rho, 4), "goodput": round(g, 4),
                         "advantage": round(advantage(w, a), 4)}
        # empirical r(D) sanity check against (1-2p)^D
        c = a - a.mean()
        row["r_emp"] = round(float(np.mean(c[D:] * c[:len(a) - D]) / np.var(a)), 4)
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--T", type=int, default=120000, help="epochs per point")
    ap.add_argument("--D", type=int, default=3, help="sensing age (epochs)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--figdir", default=r"..\..\paper\figures")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    ps = [0.005, 0.01, 0.02, 0.035, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4]
    main_sweep = sweep_p(a.D, ps, a.T, a.seed)

    # D-sweep for the collapse panel: advantage of the (optimal) threshold policy
    collapse = {}
    for D in (2, 4, 8):
        collapse[D] = [{"tau_c": tau_c_of(p), "D_over_tau": D / tau_c_of(p),
                        "advantage": r["threshold"]["advantage"],
                        "predicted": r["predicted"]}
                       for p, r in zip(ps, sweep_p(D, ps, a.T, a.seed + D))]

    result = {"D": a.D, "T": a.T, "sweep": main_sweep, "collapse": collapse}
    with open(os.path.join(a.outdir, "tau_sweep_results.json"), "w") as f:
        json.dump(result, f, indent=2)

    # ---- console summary -------------------------------------------------
    print(f"\n  feedback-advantage validation  (D={a.D}, T={a.T})")
    print(f"  {'tau_c':>7} {'r_emp':>6} {'pred':>6} | "
          f"{'thresh':>7} {'aimd':>7} {'adapt':>7}   (advantage over static)")
    for r in main_sweep:
        tc = r["tau_c"]
        print(f"  {tc:7.1f} {r['r_emp']:6.3f} {r['predicted']:6.3f} | "
              f"{r['threshold']['advantage']:7.3f} {r['aimd']['advantage']:7.3f} "
              f"{r['adaptive']['advantage']:7.3f}")
    # headline gap between the theory and the optimal controller
    gap = max(abs(r["threshold"]["advantage"] - r["predicted"]) for r in main_sweep)
    print(f"\n  max |threshold_advantage - 1/2 r(D)| = {gap:.4f}  "
          f"(theory match; smaller is better)")

    _figure(main_sweep, collapse, a)


def _figure(sweep, collapse, args) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:                                   # noqa: BLE001
        print(f"[fig] matplotlib unavailable ({e}); JSON written, skipping plot")
        return
    tc = [r["tau_c"] for r in sweep]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    ax1.plot(tc, [r["predicted"] for r in sweep], "k--", lw=1.6,
             label=r"theory $\frac{1}{2} r(D)=\frac{1}{2} e^{-D/\tau_c}$")
    ax1.plot(tc, [r["threshold"]["advantage"] for r in sweep], "o-", ms=4,
             label="delayed-threshold (Bayes-opt)")
    ax1.plot(tc, [r["aimd"]["advantage"] for r in sweep], "s-", ms=4,
             label="AIMD (practical)")
    ax1.plot(tc, [r["adaptive"]["advantage"] for r in sweep], "^-", ms=4,
             label="regime-adaptive")
    ax1.axhline(0, color="0.6", lw=0.8)
    ax1.set_xscale("log")
    ax1.set_xlabel(r"capacity coherence time $\tau_c$ (epochs)")
    ax1.set_ylabel(r"goodput advantage over static $\Delta$")
    ax1.set_title(fr"feedback value vs. predictability ($D={args.D}$)")
    ax1.legend(fontsize=7, loc="upper left")
    ax1.grid(alpha=0.3)

    for D, rows in collapse.items():
        x = [r["D_over_tau"] for r in rows]
        ax2.plot(x, [r["advantage"] for r in rows], "o", ms=4, label=f"$D={D}$")
    xs = np.linspace(0.02, 6, 200)
    ax2.plot(xs, 0.5 * np.exp(-xs), "k--", lw=1.6, label=r"$\frac{1}{2} e^{-D/\tau_c}$")
    ax2.set_xlabel(r"sensing age / coherence  $D/\tau_c$")
    ax2.set_ylabel(r"$\Delta$ (threshold)")
    ax2.set_title("scaling collapse across $D$")
    ax2.legend(fontsize=7)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    figdir = args.figdir
    os.makedirs(figdir, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(figdir, f"tau_sweep.{ext}"), dpi=150,
                    bbox_inches="tight")
    print(f"[fig] wrote {os.path.join(figdir, 'tau_sweep.pdf')}")


if __name__ == "__main__":
    main()
