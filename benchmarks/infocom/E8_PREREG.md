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
