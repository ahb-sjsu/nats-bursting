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
