# E8 protocol — contention generator + end-to-end goodput↔compliance

Validates the paper's central claim: the AIMD admission controller (§4) maximizes
goodput while keeping the over-admission rate ρ ≤ ε, **dominates** naive/static
baselines, and the measured ρ tracks the Prop. 2 prediction. This is the headline
experiment; it requires a cluster and is run only when an NRP namespace (or an
equivalent owned cluster) is greenlit.

## Why a contention generator
On a real multi-tenant cluster the productive capacity $a_t$ (slots the scheduler
will give the guest) is **exogenous** — set by other tenants, not us. To get a
*reproducible, ground-truth* $a_t$ we bound our own slice and inject a **controlled
competitor** inside it: a co-workload that holds a known, time-varying number of
GPU slots $c(t)$, so available capacity is $a(t) = C - c(t)$ with $C$ the slice
size. Because we set $c(t)$, $a(t)$ is known exactly — which is what lets us check
the Prop. 2 bound rather than merely observe behavior.

## Capacity model & policy budget
- Contended pool size **C** (GPU slots). Single identity is capped at **K = 4**
  pods, so **C ≤ 4** with one account; competitor uses $c(t)$, guest uses the
  rest. For larger C, use a **second cooperating namespace/identity** (competitor
  in one, guest in the other) — call it out explicitly in the writeup.
- Guest jobs request 1 GPU each; competitor jobs request 1 GPU each.
- **Compliance invariant (must hold every epoch):** competitor + guest pods ≤ K;
  every pod runs *real compute* and exits 0 (no `sleep` → ban); every running pod
  sustains util ≥ 40% (GPU floor U); storage cleaned post-run.

## Contention profiles c(t)
| profile | c(t) | tests |
|---|---|---|
| `square` | alternates $c_{lo}\!\leftrightarrow\!c_{hi}$ every τ epochs | step response: convergence speed + back-off depth |
| `ramp` | linear $c_{lo}\to c_{hi}$ | the bounded-variation extension ($|a_{t+1}-a_t|\le\delta$) |
| `poisson` | arrivals λ, hold H (exp) | realistic burstiness |
Competitor holds slots with **real matmul** for the scheduled duration, then
exits 0. Profile phase is randomized per repeat.

## Policies under test (the `--baseline` axis already in run.py)
- **naive** — submit all B at once ($w=B$); expected to breach the cap/floor under contention.
- **static** — fixed window $w_{\text{static}}$ (or rate r); under-utilizes when $a(t)$ rises.
- **aimd** — §4 controller, params $(\alpha,\beta,w_{\min},K)$; congestion signal =
  pod pending > τ **or** measured util < U, detected with delay D.

## Metrics (per run; sampled once per control epoch via the prober + pod status)
- **Goodput** $G$ = productive GPU-seconds (pods running with util ≥ U).
- **Burst-completion** $T$ = wall time to B results.
- **Sustained GPU utilization** (compliance witness; must stay ≥ 40%).
- **Over-admission rate** $\rho$ = fraction of epochs with ≥1 *non-productive* held
  pod (pending, or running with util < U). This is the operational ρ of Prop. 2.
- **Cold-start**, **submit→first-result** (already emitted by run.py E8).
- **Violations**: max concurrent pods (≤ K?), util-floor breaches, any non-exit-0.

## Prop. 2 validation — the money plot
1. Pre-measure **D** (E7 with `--induce-load`, under live GPU load).
2. For chosen $(\alpha,\beta)$ predict $\rho_{\text{pred}} \approx \dfrac{D\,\alpha}{(1-\beta)\,\bar a}$,
   with $\bar a$ the time-average of the *known* $a(t)$.
3. Run **aimd**, measure $\rho_{\text{obs}}$.
4. Plot $\rho_{\text{obs}}$ vs $\rho_{\text{pred}}$ across profiles and an $(\alpha,\beta)$
   sweep → does the bound hold and track?
5. **Headline figure:** goodput vs ρ (Pareto), all three policies, with the
   feasibility line ρ = ε. Claim succeeds iff aimd sits on the upper-left frontier
   (high goodput, low ρ) and the others do not.

## Testbed options
- **Primary (controlled, reproducible $a(t)$):** a capacity-bounded NRP namespace
  (C set by quota) or a single-node k3s we own. Preferred for the core claim.
  Prefer **NRP A10×8** over Atlas-2×GV100 — Atlas's two GPUs under sustained matmul
  hit the thermal envelope (the §6 Kalman controller would engage and *confound*
  the admission measurement; note it, or disable on the competitor).
- **Secondary (external validity, observational):** real NRP under *natural* load.
  $a(t)$ is uncontrolled; estimate $\hat a(t)$ from the prober and report each
  policy's goodput + ρ over matched time windows. No ground-truth, so the Prop. 2
  check uses $\hat a$ and is reported as corroborating, not definitive.

## Statistics
- ≥ 5 repeats per (policy × profile); mean ± 95% CI via the existing `multiseed.py`
  machinery. Report ρ and completion as distributions, not just means (the tail is
  the story). Randomize profile phase per repeat.

## Run procedure (operational, once greenlit)
1. (pre) E7 `--induce-load` → D.
2. Bring up the result responder, the nats-bursting control plane, and the namespace.
3. For each profile × policy × rep:
   a. start `contention.py --profile P --C <C> --epochs N` (logs realized c(t) → ground-truth a(t));
   b. concurrently `run.py -e E8 --baseline <policy> --burst B --kcap <K-c_max> ...`
      (submits, drains results, samples prober per epoch);
   c. collect metrics; tear down competitor + guest; assert clean (0 pods, exit-0, storage purged).
4. Aggregate → goodput–ρ Pareto + ρ_obs-vs-ρ_pred plot.

## Threats to validity (state these in the paper)
- C ≤ 4 single-identity is a small pool; scale via a second namespace and say so.
- Atlas thermal coupling can confound; prefer NRP, or pin the §6 controller off on competitors.
- The observational NRP arm lacks ground-truth $a(t)$.
- The competitor is *cooperative* (we control it); real tenants are adversarial/uncorrelated — the controlled arm is a lower bound on difficulty, the observational arm the upper.
