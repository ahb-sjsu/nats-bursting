# E8 pre-registration (written before the run)

Registered before executing the larger sweep, so the analysis can't move goalposts.
This is a deterministic systems benchmark, so literal clinical double-blinding does
not apply (no human subjects, no placebo); we adopt its valid analogs: **randomized
interleaved trial order**, a **fixed decision rule stated up front**, **all trials
reported**, and **coded aggregation** (analyze by opaque label, unblind last).

## Configuration (fixed)
- Policies: `naive`, `static`, `aimd`. Reps: 4 each → 12 trials.
- Burst B = 9 jobs; politeness budget **C = 2**; naive hard ceiling H = 3 (≤ fair-use cap 4).
- Worker: real GPU matmul, HOLD_SEC=15, MATMUL_SIZE=4096, pinned `nvidia.com/gpu.product=NVIDIA-A10`.
- `static` submit rate = 0.05 jobs/s (≈ 1 every 20 s → expected concurrency < budget).
- Trials run **sequentially** (≤3 pods at any instant; fair-use compliant), each with a
  unique `--run-tag` (no cross-trial job-name collisions) and clean-up before/after.
- **Randomized interleaved order (seed 42, fixed):**
  `static4 static2 naive3 aimd1 aimd2 static3 aimd4 naive4 static1 naive1 naive2 aimd3`

## Metrics (fixed)
- **goodput** = completed / burst_completion_s (tasks/s).
- **over-budget ρ** = fraction of monitored epochs with running concurrency > C (=2).
- A trial whose result-drain times out (completion = None) is **reported as a failure**
  and **excluded from goodput means** (counted in a failure tally), not silently dropped.

## Hypotheses + decision rules (fixed)
- **H1 (aimd beats static on goodput at equal politeness):** declared SUPPORTED iff
  `mean(goodput_aimd) > mean(goodput_static)` **and** their 95% CIs are disjoint, with
  both ρ ≈ 0.
- **H2 (naive is impolite):** declared SUPPORTED iff `mean(ρ_naive) > 0` and its 95% CI
  is disjoint from aimd's and static's (≈0).
- **Null/negative outcomes will be reported as such** (e.g., if aimd ≈ static, H1 is NOT
  supported — stated plainly).

## Analysis
Aggregate all 12 trials by policy → mean ± 95% CI (t, df=reps−1). Apply the rules above.
Report the full per-trial table regardless of outcome.

---

# Pre-registration — Run 2 (compute-dominated), written before running

Run 1 returned a pre-registered NULL: goodput was overhead-bound (per-pod startup
~20 s ≈ the 10 s compute). Run 2 fixes the *conditions* (not the hypotheses): make
compute ≫ overhead so concurrency maps to goodput, and pods overlap during the long
compute so peak concurrency reflects the policy.

## Changes from Run 1 (only conditions)
- **HOLD_SEC = 90** (was 10) — compute now ~4-5x the ~20 s startup overhead.
- B = 4, budget C = 2, naive ceiling H = 3 (unchanged); RTX-3090 (pre-flight-checked free).
- `static` rate = 0.011 jobs/s (≈ 1 per 90 s → expected ~1 concurrent, < budget 2).
- 3 reps; randomized interleaved order, **seed 43** (fresh); unique `--run-tag`; clean-up between.

## Hypotheses + decision rules — UNCHANGED from Run 1
- H1: aimd goodput > static goodput, 95% CIs disjoint, both ρ≈0.
- H2: naive ρ > 0, CI disjoint from aimd/static (≈0).
- Null/negative reported as such. All trials reported (timeouts included).

---

# Pre-registration — Runs 3 & 4 (Atlas controlled testbed), before running
Diagnosis after 3 NRP nulls: shared-cluster variance (scheduling + cold image pull)
dominates. Move to a controlled, variance-free testbed (Atlas local processes).
- **Run 3 (GPU):** 2x GV100, budget C=2, hard-cap 3, B=4, HOLD=30, seed 44, 4 reps.
- **Run 4 (CPU):** 48 cores, budget C=8, hard-cap 12, B=12, HOLD=20, 1 thread/proc, seed 45, 4 reps.
- Hypotheses + decision rules UNCHANGED (H1, H2). All trials reported.
