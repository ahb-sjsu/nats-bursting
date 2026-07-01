# E9 pre-registration — in-situ contended goodput–politeness Pareto

**Purpose.** E8 measured politeness in the *abundance* regime (fixed self-imposed
budget, capacity never scarce). E9 measures it under **real, time-varying contention**
on a controlled testbed: a competing tenant occupies part of a 2-GPU pool so the
guest's available capacity `a(t)` is exogenous and scarce — the **scarcity regime**
that Prop. 2's over-admission bound actually targets. This closes the paper's #1
evaluation gap.

## Testbed
- 2× NVIDIA GV100 (capacity `C = 2` slots; one full-speed job per GPU).
- A **competitor** process generator occupies `c(t) ∈ {0,1,2}` GPUs on a fixed
  profile; ground-truth available capacity `a(t) = C − c(t)`.
- The **guest** bursts `B` fixed-work GPU tasks under one admission policy.
- Micro tier: batch-probe `ThermalController`, driven by **GPU temperature**,
  caps guest concurrency to hold a thermal setpoint while the macro loop admits.
- Contamination control: the resident (idle) LLM stack on GPU0 is never touched;
  its GPU utilization is sampled every epoch and any trial in which it exceeds
  10% is discarded and re-run (reported).

## Policies (guest)
- **naive** — keep the hard cap `K = C` in flight, ignore occupancy.
- **static** — fixed submit rate, occupancy-blind.
- **aimd** — probe measured GPU occupancy (nvidia-smi), completion-gated
  admission; additive-increase on clean epochs, multiplicative-decrease on a
  congestion signal (in-flight would exceed measured available).

## Profiles for `c(t)`
- **square** — alternates `c_lo=0` / `c_hi=1` every `τ` epochs (predictable scarcity).
- **poisson** — on/off competitor arrivals (unpredictable scarcity + non-stationary).

## Metrics
- **goodput** = guest tasks completed / wall-clock (tasks/s). Sensitive to
  contention: an over-admitted task time-shares a GPU and slows.
- **over-admission ρ** = fraction of epochs with guest in-flight `n_t > a(t)`
  (ground truth), i.e. the Prop. 2 quantity, now in the scarcity regime.
- **competitor slowdown** = competitor throughput vs. its uncontended baseline
  (the *impoliteness* the guest inflicts on the other tenant).
- **thermal** = peak/mean GPU temperature and the fraction of epochs the micro
  tier throttled; setpoint must not be exceeded.
- **bound check** = measured ρ vs. predicted `ρ̂ = Dα/((1−β)·ā)` using the
  measured detection delay `D` and the realized mean available `ā`.

## Hypotheses (pre-registered, one-sided unless noted)
- **H1 (efficiency):** aimd goodput > static goodput at equal politeness (both
  ρ ≈ 0), under contention. Disjoint 95% CIs.
- **H2 (politeness):** naive over-admits under contention (ρ > 0 with a
  meaningful margin) and inflicts measurable competitor slowdown; aimd does not
  (ρ ≈ 0, competitor slowdown ≈ 0).
- **H3 (bound):** measured ρ for aimd/naive is consistent (same order,
  within ~2×) with the Prop. 2 prediction `ρ̂` computed from measured `D, ā`.
- **H4 (two-tier):** with the thermal micro tier enabled, peak GPU temperature
  stays ≤ setpoint while goodput is within noise of the thermally-unbounded run
  when the setpoint is not binding (control is free when there is thermal room).

## Design / rigor
- Profiles × policies fully crossed; **≥4 repeats** per cell.
- **Randomized interleaved** trial order across (policy, profile, seed); seeds
  42/43/44/45. Each trial tagged; **all** trials reported including discards/nulls.
- Fixed `B`, `τ`, task work `W`, and setpoint across policies within a profile.
- One policy+profile+seed per process invocation (no cross-trial state).

## Decision rule
Report the full goodput–ρ frontier per profile. Claim the politeness result only
if H1 and H2 both hold with disjoint CIs in ≥2 profiles; report H3/H4 as
obtained (including if the bound is loose or the setpoint never binds), without
suppression.
