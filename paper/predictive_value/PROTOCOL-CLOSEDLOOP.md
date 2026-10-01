# Closed-loop queue experiment: registered protocol

Registered 2026-10-01, before any simulation was run. Companion to
`submission/sigmetrics.tex`, Section "Closed loop: what transfers, and what
does not" (`sec:closedloop`): Proposition `prop:clstep` (per-step decision
value of delayed information is bounded by Omega*sqrt(I/2) under the law the
closed-loop policy induces) and Proposition `prop:clsteer` (the steering
value has no such bound). This experiment does not change the paper.

The design below is adopted as written. Implementation choices that the
design leaves open are fixed in "Implementation details" before running.

## System

- Discrete-time bottleneck queue, capacity K = 20, occupancy X_t in {0..K}.
- Each slot, in order:
  1. the controller observes its information G_t and chooses w_t in {0,1};
  2. the step reward R_t(w_t, X_t) = w_t * (1 - 2 X_t / K) is earned
     (range [-1, 1], Omega = 2);
  3. arrivals: the sent packet (if w_t = 1), then an exogenous cross-traffic
     packet with probability lambda_c = 0.3, each dropped if the queue is full;
  4. one packet departs with probability mu = 0.5 if the queue is nonempty.
- So X_{t+1} depends on w_t (closed loop) and w_t does not affect X_t.

## Information and delay

- Delay D in {0, 1, 2, 4, 8, 16, 32, 64}.
- G_t = (X_{t-D}, w_{t-D}, ..., w_{t-1}).

## Policy classes (grid search per D)

- (O) open loop: send with fixed probability p, p in {0, 0.01, ..., 1} (101 values).
- (F1) send iff X_{t-D} < theta, theta in {0, ..., K+1} (22 values).
- (F2) send iff xhat_t < theta, where
  xhat_t = clip(X_{t-D} + sum_{s=t-D}^{t-1} w_s + D (lambda_c - mu), 0, K),
  theta on a 0.25 grid in [0, K+1] (85 values).
- For D = 0, F1 = F2 (both thresholds on X_t; reported for both).

## Simulation

- 4 independent seeds 20261001, 20261002, 20261003, 20261004.
- Each seed: 1e4 burn-in slots, then 2e5 measured slots.
- Common random numbers across all policies within a seed.
- Selection: best parameter per class by mean measured reward per slot over
  seeds 1-2 (20261001, 20261002).
- Evaluation: the selected policies on seeds 3-4 (held out); all reported
  values are held-out values.

## Measurements (per D, held-out seeds, best feedback policy = best of F1/F2 by held-out value)

1. Dynamic gain per slot g_dyn = V(best feedback) - V(best open loop).
2. Statistic S_t = (X_{t-D}, A_t), A_t = number of own sends in the last D
   slots (A_t = 0 for D = 0). Plug-in mutual information I(X_t; S_t) (nats)
   from the empirical joint under the selected feedback policy, and the
   per-step envelope Omega * sqrt(I/2).
3. Per-step myopic decision value for S_t-measurable one-step actions under
   the same induced law, exactly from the empirical joint:
   Delta = E_S[max(0, E[1 - 2X/K | S])] - max(0, E[1 - 2X/K]) (immediate
   reward only).
4. Bootstrap 95% intervals for g_dyn and Delta over the 2 held-out seeds x 20
   blocks (40 blocks of 1e4 slots).

## Pre-stated readings

- (A) `prop:clstep` predicts Delta <= Omega*sqrt(I/2) at every D on the
  plug-in law. This is a consistency check; a failure means a bug.
- (B) `prop:clsteer` makes no directional prediction for this system. We
  report g_dyn, Delta and the envelope at every D, and the steering share
  1 - Delta/g_dyn where g_dyn > 0, as descriptive results.
- (C) We expect g_dyn to decrease toward zero as D grows (stale feedback
  cannot steer); we report whether it does.

## Implementation details (fixed before running)

- Initial state for every policy and seed: X = 0, delayed-observation buffer
  all 0, past-action buffer all 0 (so A starts at 0); the 1e4 burn-in slots
  wash this out and are not measured.
- Common random numbers: per seed, three uniform streams of length
  1e4 + 2e5 are drawn once (numpy default_rng(seed)): U_open (open-loop send
  iff U_open[t] < p), U_cross (cross packet iff U_cross[t] < 0.3), U_dep
  (departure iff U_dep[t] < 0.5). Every policy uses the same streams.
- Selection ties are broken by the smallest parameter value.
- Phase 1 simulates every grid point on seeds 1-2. Phase 2 re-simulates only
  the three selected policies (O, F1, F2) on seeds 3-4 with the same
  streams-per-seed rule, recording per-block reward sums and per-block joint
  counts of (X_{t-D}, A_t, X_t).
- Bootstrap: 2000 resamples of the 40 held-out blocks with replacement
  (rng seed 20261005). g_dyn is recomputed as the mean of resampled
  per-block differences (same blocks for both policies, so CRN is kept);
  Delta is recomputed from the resampled pooled counts. Intervals are the
  2.5% and 97.5% percentiles.
- Feasibility note on (2)-(3): at D = 64 the statistic S has up to
  21 x 65 = 1365 cells and the joint with X up to 28665 cells on 4e5 slots, so
  the plug-in I is biased upward. Reading (A) holds on any distribution,
  including the empirical one, so it remains an exact consistency check of
  the code; the absolute envelope at large D is reported as a plug-in
  quantity, not as an estimate of the population information.
- Compute: Atlas only, CPU, joblib n_jobs <= 4, BLAS threads = 1, in screen
  session `pvcl`, directory /archive/infocom_battery/closedloop/.
- No parameter, grid or reading is changed after seeing held-out results.
