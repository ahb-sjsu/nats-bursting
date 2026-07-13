# Live adaptive-controller curve check — NEGATIVE result (rig bug, not theory/controller)

**Question:** do the *live* (Atlas GPU) regime-adaptive points land on the feedback-usefulness
curve `Δ(D) = ½·r(D)`, `r(D) = (1-2p)^D`?

**Answer: no — and the reason is an experimental-rig bug, not the law or the controller.**
The sim-level validator (`tau_sweep.py`, where `a_t` *is* the DTMC) confirms the law cleanly.
The live rig fails to *realize* the intended capacity process, so the sweep never traces the curve.

## What the live sweep shows (`e9_adaptive_curve.py`, D=3, γ=0.15, 2 seeds/point)

| p (nominal) | r_true=(1-2p)³ | ½·r(D) | r̂ (online) | frac_closed | g_static | g_aimd | g_adaptive |
|---|---|---|---|---|---|---|---|
| 0.01 | 0.941 | 0.471 | 0.743 | 0.99 | 0.0652 | 0.0715 | 0.0714 |
| 0.03 | 0.831 | 0.415 | 0.779 | 0.99 | 0.0636 | 0.0817 | 0.0815 |
| 0.08 | 0.593 | 0.296 | 0.745 | 0.99 | 0.0637 | 0.0794 | 0.0760 |
| 0.15 | 0.343 | 0.171 | 0.683 | 0.99 | 0.0652 | 0.0569 | 0.0568 |
| 0.40 | 0.008 | 0.004 | 0.685 | 0.99 | 0.0637 | 0.0583 | 0.0604 |

- **r̂ is ~flat (0.68–0.78) across all p** — mean `|r̂ − r_true| = 0.284`. It does **not** sit on the
  `(1-2p)³` curve. At p=0.4 the realized signal should be near-uncorrelated (r_true≈0.008) but the
  controller estimates r̂≈0.69.
- **The regime switch never fires:** `frac_closed_loop = 0.99` at *every* p, so adaptive ≡ AIMD.
- **Consequence:** in the (nominal) untrackable regime the failure to fall back to static **costs
  goodput** — adaptive (0.057, 0.060) < static (0.065, 0.064) at p=0.15 and 0.40.

## Root cause — the markov process isn't realized on the GPU

`e9_contended.py::reconcile_comp` is **add-only** and competitors have a **fixed life**
(`comp_life = 25 s`): "over-target competitors simply self-expire; no kill." So when the DTMC target
(`c_target`, flipped per-epoch with prob `p_flip`) goes high, a competitor launches and then **squats
for ~25 s regardless of subsequent flips**. Realized GPU availability therefore flips at the
`comp_life` cadence (~11 flips / 233 s ≈ every 21 s), **decoupled from `p_flip`**. That is why r̂ is
constant across the sweep: the independent variable never actually moves the quantity the controller
senses.

The online estimator itself is correct (it counts flips in the age-D availability stream and forms
`r̂=(1-2p̂)^D`); it is faithfully reporting a signal the rig fails to vary.

## Fix (follow-up, not yet run)

Make the competitor occupancy track the DTMC so realized `r(D)` matches theory:
- make `reconcile_comp` **symmetric** — kill over-target competitors when the target flips low
  (instead of add-only + fixed-life expiry); **or**
- bind `comp_life` to the flip (competitor expires when `c_target` goes low), i.e. drive competitor
  on/off directly from `mk_state`.

Then re-run the markov sweep and re-check that r̂ lands on `(1-2p)^D` and the switch fires for
`r_true < γ`. Until then, **only the sim-level `Δ(D)=½·r(D)` validation (`tau_sweep.py`) is sound**;
the live markov numbers here are reported as a diagnosed rig artifact, not a controller result.

Figure: `paper/figures/e9_adaptive_curve.{pdf,png}` (left: r̂ off the curve; right: adaptive≡aimd,
losing to static at high p).
