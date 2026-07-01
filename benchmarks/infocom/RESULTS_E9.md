# E9 results — in-situ contended goodput–politeness Pareto

Controlled contention on a 2×GV100 node (capacity `C=2`): a competing tenant
occupies `c(t)∈{0,1}` GPUs on a fixed profile, so the guest's available capacity
`a(t)=C−c(t)` is exogenous and scarce. Guest bursts 16 fixed-work tasks under each
policy; aimd probes GPU occupancy by a per-GPU process census (detection delay `D`
≈ 2–3 s). Pre-registered (`E9_PREREG.md`), randomized-interleaved, **4 seeds/cell**,
**27 trials, 0 contaminated** (resident ego stack monitored by PID; never touched).
Params: `--burst 16 --work 1000 --matmul 4096 --tau 25 --comp-life 25 --gpus 1,0`.

## Results (mean ± 95% CI, n=4)

| contention | policy | goodput (tasks/s) | ρ (over-admit) | neighbour kept |
|---|---|---|---|---|
| square (structured) | naive | 0.101 ± 0.002 | 0.64 ± 0.01 | 0.62 |
| | **aimd** | **0.091 ± 0.000** | **0.15 ± 0.01** | **0.76** |
| | static | 0.064 ± 0.000 | 0.11 ± 0.01 | 0.89 |
| poisson (memoryless) | naive | 0.096 ± 0.002 | 0.85 ± 0.06 | 0.62 |
| | aimd | 0.062 ± 0.006 | 0.30 ± 0.06 | 0.55 |
| | static | 0.064 ± 0.000 | 0.22 ± 0.04 | 0.79 |

## Hypotheses
- **H1 (aimd > static goodput):** ✅ **square** — 1.41× (0.091 vs 0.064), disjoint CIs.
  ❌ **poisson** — pre-registered **null**: aimd 0.062 vs static 0.064, overlapping CIs.
- **H2 (naive impolite, aimd polite):** ✅ naive ρ=0.64–0.85 and steals ~38% of the
  neighbour in both regimes; aimd cuts over-admission ~4× (square) and spares the
  neighbour (76% kept). Under poisson aimd's advantage collapses (see H1).
- **H3 (bound):** measured `D≈2–3 s` puts the Prop. 2 ceiling above the observed aimd
  ρ; the bound is conservative for a discrete completion-gated controller, but its
  central prediction — ρ grows as contention outpaces `D` — is borne out
  (square 0.15 → poisson 0.30).
- **H4 (two-tier live):** micro tier (batch-probe `ThermalController`) active
  throughout the GPU burst (throttled >90% of epochs; also lowered aimd ρ
  0.15→0.08). On CPU (native actuator) it throttled predictively behind a hard
  safety cutout; the shared node's co-tenant baseline (~77 °C) sets a thermal floor
  self-throttling cannot undercut — a politeness lesson in itself.

## Takeaway
Feedback admission is the polite-efficient point when a neighbour's load has
structure to track, and one should fall back to a fixed budget when it does not.
naive's higher goodput is bought entirely at the neighbour's expense. Honest
negative (poisson) reported, not suppressed.

Atlas restored to captured baseline after the run (GPU0 60 °C/0%/19621 MiB, GPU1
free; ego stack intact; zero strays).
