# E8 — end-to-end goodput vs politeness on NRP (first real run)

First end-to-end E8 on live NRP A10 GPUs through the full nats-bursting stack:
home `Client.submit` → Atlas hub → NRP leaf → controller → guest Job (GPU worker:
real matmul, publishes `results.<job_id>`) → result routed home; the home driver's
shared `Monitor` samples guest-pod concurrency each second. 3 reps/policy, B=3 jobs,
budget **C=2**, hard cap K=4, all pods pinned to `nvidia.com/gpu.product=NVIDIA-A10`,
sequential (≤3 pods at once), real compute + exit-0 (fair-use compliant). Raw JSON in
`out/E8_*_r*.json`; figure `out/agg_e8/pareto.png`.

## Regime (important, honest framing)
NRP allocates GPUs **exclusively** and has **abundant** A10s, so our few pods never
hit hardware scarcity. We therefore test the **politeness-budget under abundance**
regime: a guest should self-limit to a budget **C** even when more is free (NRP bans
over-grabbing / under-utilization). "Over-admission" ρ = fraction of epochs guest
concurrency exceeds the budget C. (The scarcity/back-off regime of the model is not
exercised here — we could not manufacture controlled scarcity without admin
ResourceQuota rights, which the portal identity lacks.)

## Result (3 reps, mean ± 95% CI; over-budget rho)
| policy | goodput (tasks/s) | over-budget rho | completion (s) | peak conc. |
|---|---|---|---|---|
| naive  | 0.10 ± 0.01 | 0.61 ± 0.24 | 31.2 ± 4.0 | 3 |
| aimd   | 0.05 ± 0.00 | 0.00 ± 0.00 | 55.2 ± 4.9 | 2 |
| static | 0.05 ± 0.00 | 0.00 ± 0.00 | 55.0 ± 0.0 | 2 |

**Finding.** `naive` buys ~1.8x goodput by exceeding the budget (peak 3, ρ≈0.61) —
the impolite-but-fast corner. The completion-gated controller (`aimd`) and the
rate-limited `static` hold the budget (peak 2, ρ=0) — the polite region. The
goodput↔politeness tradeoff is real and measured on production GPUs.

## Honest limitations (this is a first, small run)
1. **aimd and static do not separate** at B=3/C=2 — both stay ≤2 with the same
   goodput. The paper's intended "aimd fills the budget better than static's trickle"
   needs a **larger B and a starker static rate** so static visibly leaves the budget
   idle while aimd keeps it full. As run, we show *polite vs impolite*, not *aimd > static*.
2. **Result-delivery flakiness**: 1/9 runs (`aimd_r2`) timed out at 2/3 — one result
   never arrived. Needs hardening (retry/ack on the result path) before scaling reps.
3. **Small scale**: B=3, ≤3 pods, short 15 s jobs — fair-use-bounded; CIs are thin.
4. **Driver, not theory**: an earlier run was discarded — the open-loop policy
   schedules didn't enforce concurrency (aimd peaked at 3) and the result drain wasn't
   scoped (counted stray results). Both fixed (completion-gated in-flight limiter +
   run-scoped drain); this run uses the corrected driver.

## What works (verified live)
Controller + RBAC, node-targeting (A10 pinning), GPU worker (matmul + publish), the
federated result path, and the concurrency Monitor — all confirmed end-to-end. The
remaining work is *experimental* (separate aimd/static at scale; harden result
delivery), not systems plumbing.
