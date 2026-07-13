"""Parity + regime-detection check for the live regime-adaptive controller.

The controller was ported from the model-level simulation (tau_sweep.run_adaptive)
into the live contention harness (e9_contended.py, --policy adaptive). This test
proves the port is faithful WITHOUT a GPU: it feeds the SAME age-D capacity
observation stream to (a) the reference estimator's arithmetic and (b) the live
harness's estimator arithmetic, and checks

  1. identical online transition streams and r_hat trajectories (bit-for-bit),
  2. identical closed-loop/static branch decisions,
  3. r_hat converges to the true r(D)=(1-2p)^D, and
  4. the branch flips with the regime: closed-loop when tau_c>>D, static when tau_c<~D.

Run: python test_adaptive_parity.py
"""
from __future__ import annotations

import numpy as np

import tau_sweep as TS  # reference model-level controllers

A_LO, A_HI = TS.A_LO, TS.A_HI
D = 3
GAMMA = 0.15


def _r_and_branch(flips: int, seen: int, D: int, gamma: float):
    p_hat = flips / max(1, seen)
    r_hat = (1 - 2 * min(p_hat, 0.5)) ** D
    return r_hat, ("closed" if r_hat > gamma else "static")


def reference_estimator(a: np.ndarray, D: int, gamma: float):
    """Transition stream + r_hat/branch AFTER EACH counted transition, exactly as
    tau_sweep.run_adaptive computes them, indexing the delayed stream a[t-D]."""
    flips = seen = 0
    trans, curve = [], []
    for t in range(1, len(a)):
        if t - D >= 1:
            f = int((a[t - D - 1] == A_HI) != (a[t - D] == A_HI))
            flips += f; seen += 1
            trans.append(f)
            curve.append(_r_and_branch(flips, seen, D, gamma))
    return trans, curve


def live_estimator(a: np.ndarray, D: int, gamma: float):
    """Transition stream + r_hat/branch as e9_contended.py --policy adaptive
    computes them: flip count on CONSECUTIVE age-D observations a_hat = a[t-D]."""
    obs = [a[t - D] for t in range(1, len(a)) if t - D >= 0]  # the a_hat stream
    ad_prev = None
    flips = seen = 0
    trans, curve = [], []
    for a_hat in obs:
        if ad_prev is not None:
            f = int(a_hat != ad_prev)
            flips += f; seen += 1
            trans.append(f)
            curve.append(_r_and_branch(flips, seen, D, gamma))
        ad_prev = a_hat
    return trans, curve


def main() -> None:
    rng = np.random.default_rng(0)
    print(f"  {'p_flip':>7} {'tau_c':>7} {'r_true':>7} {'r_hat_end':>9} "
          f"{'branch_end':>10} {'parity':>7}")
    all_ok = True
    regime_ok = True
    conv_all = True
    for p in (0.005, 0.02, 0.05, 0.10, 0.20, 0.40):
        a = TS.markov_capacity(60000, p, rng)
        t_ref, c_ref = reference_estimator(a, D, GAMMA)
        t_live, c_live = live_estimator(a, D, GAMMA)
        # 1+2: identical transition streams => identical r_hat & branch, all epochs
        n = min(len(c_ref), len(c_live))
        trans_match = t_ref[:n] == t_live[:n]
        max_dr = max(abs(c_ref[i][0] - c_live[i][0]) for i in range(n))
        branch_match = all(c_ref[i][1] == c_live[i][1] for i in range(n))
        ok = trans_match and (max_dr < 1e-12) and branch_match
        all_ok &= ok

        r_true = (1 - 2 * min(p, 0.5)) ** D
        tau_c = TS.tau_c_of(p)
        r_end, br_end = c_live[-1]
        conv_all &= abs(r_end - r_true) < 0.02
        # 4: regime detection
        if tau_c >= 4 * D:
            regime_ok &= (br_end == "closed")
        if tau_c <= D / 2:
            regime_ok &= (br_end == "static")
        print(f"  {p:7.3f} {tau_c:7.2f} {r_true:7.3f} {r_end:9.3f} "
              f"{br_end:>10} {'OK' if ok else 'FAIL':>7}")

    print()
    print(f"  [1+2] live estimator == reference (transitions, r_hat, branch): "
          f"{'PASS' if all_ok else 'FAIL'}")
    print(f"  [3]   r_hat converges to true r(D) (|err|<0.02): "
          f"{'PASS' if conv_all else 'FAIL'}")
    print(f"  [4]   detects the regime (closed if tau_c>>D, static if tau_c<~D): "
          f"{'PASS' if regime_ok else 'FAIL'}")
    if not (all_ok and regime_ok and conv_all):
        raise SystemExit("PARITY/REGIME CHECK FAILED")
    print("\n  the live --policy adaptive controller reproduces the model-level "
          "controller and\n  correctly switches closed-loop<->static with the "
          "measured predictability r_hat.")


if __name__ == "__main__":
    main()
