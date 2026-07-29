# E9-F results — live matched-mismatch frontier (square contention)

Fills the gap named in the 56-Sol revision's threats-to-validity: Table 1's
1.41× was an unmatched operating-point comparison. This campaign traces the
record-independent (static trickle) curve and the AIMD feedback curve on the
same rig in one session, so goodput is compared **at equal mismatch ρ**.

Run 2026-07-29 on the 2×GV100 node under `run_frontier_suspend.sh` (ego stack
SIGSTOPed, restored on exit; failsafe 5 h). **48 trials, 0 contaminated**,
randomized interleaved, 4 seeds/cell. Parameters identical to the published
Table-1 cells: `--profile square --burst 16 --work 1000 --matmul 4096 --tau 25
--comp-life 25 --interval 1 --gpus 1,0`. Raw JSONs:
`atlas:/archive/experiments/e9_frontier/` (plus `frontier_summary.json`, a copy
committed at `e9_results/frontier_summary.json`). Driver `e9_frontier.py`,
analyzer `e9_frontier_analyze.py`.

## Record-independent curve (static `--rate` sweep)

| rate | ρ | goodput (tasks/s) |
|---|---|---|
| 0.03 | 0.031 ± 0.000 | 0.0332 ± 0.0000 |
| 0.05 | 0.066 ± 0.005 | 0.0543 ± 0.0000 |
| 0.06 | 0.092 ± 0.000 | 0.0646 ± 0.0000 |
| 0.08 | 0.360 ± 0.016 | 0.0831 ± 0.0000 |
| 0.12 | 0.486 ± 0.019 | 0.1090 ± 0.0028 |
| 0.18 | 0.482 ± 0.024 | 0.1086 ± 0.0021 |
| 0.28 | 0.487 ± 0.016 | 0.1088 ± 0.0006 |

The frontier is the **concave upper envelope** of these points plus the origin
(time-sharing between record-independent policies is itself record-independent,
so the envelope is achievable): vertices (0,0) → (0.031, 0.033) →
(0.066, 0.054) → (0.092, 0.065) → (0.486, 0.109). Note `rate 0.08`
(ρ=0.36, g=0.083) falls **below** the envelope chord — it is dominated by
time-sharing rates 0.06 and 0.12. The curve saturates at ~0.109 tasks/s
(the greedy corner) once ρ ≈ 0.49.

## Feedback curve (AIMD (α, β) sweep) and matched comparison

| (α, β) | ρ | goodput | envelope(ρ) | Δ_live | ratio |
|---|---|---|---|---|---|
| (1, 0.25) | 0.123 ± 0.005 | 0.0947 ± 0.0003 | 0.0681 | **+0.0266** | **1.39** |
| (1, 0.5)  | 0.143 ± 0.054 | 0.0944 ± 0.0014 | 0.0704 | +0.0241 | 1.34 |
| (1, 0.75) | 0.150 ± 0.053 | 0.0943 ± 0.0012 | 0.0712 | +0.0231 | 1.32 |
| (2, 0.5)  | 0.142 ± 0.056 | 0.0940 ± 0.0009 | 0.0703 | +0.0238 | 1.34 |
| (3, 0.35) | 0.156 ± 0.063 | 0.0940 ± 0.0013 | 0.0718 | +0.0222 | 1.31 |

**Headline: at matched mismatch, the feedback branch delivers 1.31–1.39× the
best record-independent envelope** (Δ_live = +0.022 to +0.027 tasks/s). The
cleanest point is (1, 0.25): ρ CI ±0.005, Δ = +0.0266, ratio 1.39. Worst-case
corner check on (1, 0.5): even at its ρ upper CI (0.197) the envelope gives
0.0764 vs goodput lower CI 0.0930 → the advantage (+0.017) survives every CI
corner. The unmatched Table-1 ratio (1.41) barely moves when matched.

Also notable: the AIMD cluster is **insensitive to (α, β)** — all five settings
land at ρ 0.12–0.16, g ≈ 0.094. Under square contention AIMD self-regulates to
the wave's duty cycle; the knobs move ρ only slightly.

## Cross-session drift caveat

The campaign re-ran both published Table-1 cells in-session: static rate 0.06 →
(ρ 0.092, g 0.0646) vs published (0.11, 0.064); AIMD (1, 0.5) → (0.143, 0.0944)
vs published (0.15, 0.091). Goodput drifts ≤ 4% across sessions (different day,
thermal state). Within-session comparisons — everything in the tables above —
share one rig session, which is why the frontier campaign re-ran those cells
rather than importing them.
