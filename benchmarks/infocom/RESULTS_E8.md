# E8 — end-to-end on NRP: what's shown, and what isn't (honest)

The full nats-bursting stack runs end-to-end on live NRP GPUs (controller → guest Job
→ GPU worker matmul → result routed home → Monitor). That much is verified. Getting a
*clean controlled goodput–politeness Pareto* out of it, however, has not succeeded —
the cluster's overhead and scheduling variance swamp the policy signal at feasible
scale. This file reports both outcomes straight.

## What IS shown
- **System works**: controller + RBAC + node-targeting (A10/RTX-3090 pinning) + GPU
  worker (matmul + publish `results.<id>`) + federated result path + concurrency
  Monitor — all confirmed live.
- **Polite vs impolite separates** (earlier B=3 run): `naive` exceeded the budget
  (peak 3, over-budget ρ≈0.61) for ~1.8x goodput; `aimd`/`static` held it (peak 2, ρ=0).
- **The admission controller works as coded**: the completion-gated limiter holds
  `aimd` at the budget C=2 (verified, peak 2 every rep).

## What is NOT shown (pre-registered null)
Rigorous leaner sweep (RTX-3090, randomized interleaved order seed 42, B=4, C=2, 3 reps;
pre-registration in `E8_PREREG.md`):

| policy | goodput (tasks/s) | over-budget ρ | peaks |
|---|---|---|---|
| naive  | 0.046 ± 0.001 | 0.12 ± 0.26 | [3, 3, 1] |
| aimd   | 0.045 ± 0.001 | 0.00 ± 0.00 | [2, 2, 2] |
| static | 0.043 ± 0.064 | 0.00 ± 0.00 | [1, 2, 2] |

- **H1 (aimd > static goodput at equal politeness): NOT supported.** All policies land
  at ~0.045 tasks/s — goodput is **overhead-bound**, not concurrency-bound.
- **H2 (naive impolite, ρ disjoint from 0): NOT supported.** naive ρ CI includes 0
  (one rep its 3 pods came up staggered → peak 1, not 3).

**Why:** per-pod startup (image pull + scheduling + CUDA cold-start ≈ the measured 2.46 s
D, plus *staggered* pod bring-up) is ~20 s/pod — comparable to or larger than the 10 s
compute. So (a) completion time is dominated by overhead, erasing the 2-parallel-vs-
1-parallel goodput gap, and (b) actual concurrency depends on *when* pods happen to come
up, not just the submission window. The policy signal is real but **below the cluster
noise floor at this scale**.

## The fix (not yet run)
Make **compute >> overhead**: long jobs (HOLD ≈ 90–120 s) so per-pod startup is a small
fraction, completion becomes compute-bound (2-parallel `aimd` ~2x faster than 1-parallel
`static`), and pods overlap during the long compute (peak concurrency reliably reflects
the policy). Plus a freer GPU pool (RTX-3090 schedules in <1 s when probed) and a
hardened result path (publish-retry) to cut the ~1/9 result-loss timeouts. This is an
**experimental-conditions** fix, not a systems fix — the stack itself is proven.

## Honest bottom line
On a busy shared cluster with short jobs, the controlled goodput–ρ Pareto is dominated
by exogenous overhead/scheduling variance — itself a real finding about bursting on
shared infrastructure. A compute-dominated rerun on free nodes is the path to the clean
3-way result; until then, only *polite vs impolite* (not *aimd > static*) is demonstrated.

## Run 2 (compute-dominated, HOLD=90 s, RTX-3090) — also null; root cause isolated
Pre-registered (E8_PREREG.md Run 2), randomized seed 43, 3 reps. Per-policy:

| policy | goodput (tasks/s) | over-budget ρ | completion (s) | peaks |
|---|---|---|---|---|
| naive  | 0.0160 ± 0.0099 | 0.15 ± 0.66 | 263 ± 190 | [2,2,3] |
| aimd   | 0.0139 ± 0.0133 | 0.00 ± 0.00 | 317 ± 290 | [2,2,2] |
| static | 0.0108 ± 0.0001 | 0.01 ± 0.04 | 371 ± 4   | [2,3,2] |

- **H1 (aimd > static goodput): NOT supported** — aimd is *directionally* higher
  (0.0139 vs 0.0108) but its 95% CI is ±0.013 and overlaps static.
- **H2 (naive impolite): NOT supported** — naive hit peak 3 in only 1/3 reps.
- **Root cause (now isolated): cold image-pull variance.** The 3.7 GB worker image
  cold-pulls on fresh RTX-3090 nodes inject **±200–300 s** of completion variance
  (aimd completion 203–436 s purely by node-cache luck) — which swamps the policy
  goodput signal. `static` is the only *consistent* row (371 ± 4 s) precisely because
  its slow trickle pulls one pod at a time, hiding the variance.

## Final bottom line (three runs, three nulls — honest)
Three rigorous, pre-registered attempts each returned null, each defeated by a
*different* layer of exogenous shared-cluster variance: scheduling contention (A10),
then short-job overhead, then cold-pull variance. **None of the nulls implicate the
system or the controller** — they implicate the testbed.

What IS robustly demonstrated:
- **System verified end-to-end** on production NRP (controller → node-targeted GPU
  worker → matmul → federated result → Monitor).
- **The admission controller reliably enforces the politeness budget**: `aimd` held
  peak = 2, over-budget ρ = 0 in **every rep of every run**. That is the controller's
  core claim, and it is robust to the variance that defeats the goodput comparison.

What is NOT established here:
- A statistically clean goodput advantage of `aimd` over `static`. It is directional
  in every run but below the cluster's cold-start / scheduling noise floor at the
  feasible (≤4-pod, fair-use) scale. A clean Pareto needs a **controlled testbed**
  (pre-warmed image cache or dedicated nodes) — recommended future work, not pursued
  further here to avoid burning shared-cluster GPU for diminishing returns.

---

## RESOLUTION — Atlas controlled testbed: H1 and H2 SUPPORTED
The three NRP nulls were testbed variance, not the system. Re-running on a **controlled,
variance-free testbed** (Atlas, local processes via `e8_local.py` — no k8s scheduling,
no 3.7 GB image pull) gives the clean result. Pre-registered (E8_PREREG.md Runs 3-4),
randomized interleaved order, 4 reps, both GPU and CPU scales.

### GPU Pareto — 2x GV100, budget C=2 (seed 44)
| policy | goodput (tasks/s) | over-budget ρ | peak |
|---|---|---|---|
| naive  | 0.0538 ± 0.0003 | 0.54 ± 0.01 | 3 |
| aimd   | 0.0539 ± 0.0001 | 0.00 ± 0.00 | 2 |
| static | 0.0313 ± 0.0000 | 0.00 ± 0.00 | 2 |

### CPU Pareto — 48 cores, budget C=8 (seed 45)
| policy | goodput (tasks/s) | over-budget ρ | peak |
|---|---|---|---|
| naive  | 0.5779 ± 0.0062 | 0.95 ± 0.00 | 12 |
| aimd   | 0.2928 ± 0.0029 | 0.00 ± 0.00 | 8 |
| static | 0.0920 ± 0.0002 | 0.00 ± 0.00 | 3 |

- **H1 (aimd > static goodput, disjoint CIs, both ρ≈0): SUPPORTED** at both scales —
  aimd **1.72x** static (GPU) and **3.18x** (CPU), CIs disjoint.
- **H2 (naive impolite): SUPPORTED** — naive ρ = 0.54 (GPU) / 0.95 (CPU), disjoint from 0.
- **aimd is the polite-efficient frontier point**: it matches naive's goodput while
  staying within budget (GPU, GPU-bound), and delivers 3.2x static's goodput at the
  same politeness (CPU, core-surplus). naive buys goodput only by over-admitting.

Figures: `out/e8_atlas/agg/pareto.png`, `out/e8_atlas_cpu/agg/pareto.png`.

## Honest scope of the claim
This is a **controlled-testbed** demonstration of the admission *algorithm* (Atlas,
local processes). The full pod-scheduling path is *separately* verified end-to-end on
NRP (controller → node-targeted GPU worker → result). The controlled result is what
isolates the policy effect from the shared-cluster variance that (honestly) defeated the
in-situ NRP measurement — both are reported.
