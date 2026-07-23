# Paper 3 — "The Value of Delayed Information" (working title)

**Why a third paper:** the INFOCOM paper is at its hard 9-page wall; the MI
theorem (theorem.eml, 2026-07-22) and the general theory it opens cannot fit.
`notes.txt`'s assessment names the INFOCOM paper's dominant rejection mode —
"stylized symmetric-binary exercise" — and its only real inoculation: *deeper
generality*. That generality is this paper.

## Division of labor (no duplication)

| content | lives in | this paper's use |
|---|---|---|
| exact binary law Δ(D)=½r(D), threshold achievability | INFOCOM Thm 1 | **cite**; recover as special case |
| β-mixing converse (ψ, Lipschitz-in-TV, Δ≤Ωβ(D)) | INFOCOM App A | **cite**; restate the envelope in the general notation |
| layer-cake C>2 (Δ=Σπ_u r_u) | INFOCOM Prop 2 | **cite**; extend (asymmetric/multi-state exactness) |
| regret of regime-adaptive control | INFOCOM Thm 2/4 | cite only |
| E9/GPU eval, testbed | INFOCOM §Eval / SC26 | cite only |
| cross-domain confirmation (1 paragraph) | INFOCOM §Eval | **full battery here** (5 domains, surrogate calibration — /archive/infocom_battery on Atlas) |
| MI envelope via Pinsker (theorem.eml steps 1–4) | nowhere yet | **Thm 2 here, full proof** (steps 1–3 are already INFOCOM App A — cite, don't reprove beyond the envelope lemma) |
| binary tightness of MI bound to O(r³) | nowhere (this session) | Prop here |
| bit-budget corollary (data processing) | nowhere (this session) | Cor here |
| "same I, different value" non-equality | email argument, informal | **Prop here, constructive proof** |

## Skeleton status (v0.1)

- Core theorems written with full proofs: Bayes envelope; TV envelope (cited);
  **MI envelope**; bit-budget corollary; binary tightness; the two-bit
  non-identifiability construction (no universal Δ=f(I)).
- TODO: multi-state exactness beyond layer-cake; envelope-comparison section
  (β vs √(I/2) — incomparable in general, both ~r/2 for binary); cross-domain
  battery section (data exists, needs the full writeup); related work
  (Howard/VoI, AoI, remote estimation, Bialek predictive information, NCS,
  Witsenhausen delayed sharing); venue decision.
- Venue candidates: ISIT 2027 (5pp, theory-only cut), Sigmetrics/Performance
  (law+measurement aesthetic — notes.txt explicitly flags this fit), or TIT
  letter. Decide after the battery section is drafted.

## Provenance

theorem.eml (2026-07-22, self-forwarded thread "Δ(D)=f(I(Xt;Xt−D))"): the
Pinsker upgrade path + the universal-equality caution. Steps 1–3 of its proof
are verbatim INFOCOM App A (Lemma lip / Thm beta); step 4 (Pinsker+Jensen+
E[KL]=I) is the only new inequality, verified cold this session including the
binary tightness computation I = r²/2 + O(r⁴) ⇒ bound = Ω(r/2 + O(r³)).

## Review round 1 (2026-07-22) — all major points verified correct, v0.3 lands the repairs

1. **Hinge law over-claimed**: restricted to finite-action/polyhedral; smooth
   counterexample added (squared error: Δ = C²/π(1−π), exactly quadratic);
   the **trichotomy** (kink→linear / flat→dead zone / smooth→quadratic) is
   now the organizing result — a strictly better paper.
2. **Sign branches**: hinge thresholds differ by covariance sign (a⁺ vs a⁻,
   π ↔ 1−π swap); reviewer's π=0.2/p*=0.3 example included.
3. **Preview process repaired**: per-(D,K) quantifiers; MI ≤ h₂(1/K)+ln2/K
   (phase term); β(D) ≥ ½ lower bound only; β convention stated.
4. Prop noneq typo (Ω/2). 5. |r| throughout tightness.
6-10. **Battery v4** (running): majority baseline, exact 2×2 Bayes value V̂₁
   (imbalance/dead-zone aware), M=299, exact MC p (no more p=.00),
   equivalence bound U = gain+ε < 0.03 for "no detectable excess",
   witness via LCB I ≥ 2((Δ̂−ε)⁺)². env/law<1 in v3 = imbalance artifact,
   explained in text.
11. Blackwell garbling lemma added (value monotonicity, not just DPI).
12. Bit budget: H(Y) ≤ b ln2 stated; clipped bound.
13. Envelope table caption → branching structure.
14. Appendix: companion results restated (β convention, binary chain,
    layer-cake) — self-contained from [1].
Related work: AoII (Maatouk), AoI-vs-VoI (Ayan), VoI-control (Soleymani),
Radner–Stiglitz, Blackwell; positioning sharpened per review. Language:
"no detectable excess", scope = exogenous one-step bounded-reward.
**Lit-check cron (2:17am) also verifies: soleymani22/ayan19 citation details,
hinge vs Chade–Schlee, Thm 2 folklore status.**

## Review round 2 (2026-07-22) — 7.5/10, path to 8.5; v0.5 lands the repairs

MAJOR (correct): the single-lag envelope was misapplied to the k=6 history
policy. Repair = **Theorem (incremental-information envelope)**:
0 ≤ Δ_W − Δ_Z ≤ Ω√(I(X;H|Z)/2) — "incremental decision value certifies
conditional predictive information." The battery's gain column IS Δ_W−Δ_Z;
seismic conditional certificate 2(0.158−0.014)² ≈ 0.041 nats (plus total
0.176). Env-excess column reinterpreted as higher-order-dependence
signature, not violation.

Also landed: **contact-order theorem** (ψ(π+h) = ψ+ah+c±|h|^q ⇒
Δ = C^q[c₊π^{1−q}+c₋(1−π)^{1−q}]; subsumes hinge/dead-zone/quadratic +
fractional q); §6 opener fixed; ψ''>0 caveat; mixing-contracts-too fix
(distinctives = H(Y) bound, chain rule, additive budgets); boundedness
sentence softened; stats renamed (parametric bootstrap under fitted Markov
null; ε = model-calibrated, moving-block bootstrap as upgrade path);
results recalibrated ("only seismic clearly material"; "empirical dead
zone"; dropped ≫10⁶ and "exactly where physics says"); endtabular leak +
M=60/299 inconsistency fixed. 14pp clean.

## Review round 3 (2026-07-22) — 8.2/10; v0.6 lands the statistical-scope repair

- **Policy-class scoping**: estimand (ii) = Δ_{P,W} (registered six-lag
  lookup class), NOT the Bayes history value. Positives transfer upward
  (V_π ≤ V*_W) → seismic conditional certificate sound; negatives bound
  the class only → "no additional value detected by the registered
  six-lag lookup policy," never unrestricted sufficiency. Scope-of-estimand
  paragraph added; table verdicts scoped.
- **Two-tail calibration**: ε_over = q95(E) for lower certificates (exact),
  ε_under = −q05(E) for equivalence bounds; v4 recorded only ε_over and
  uses it both sides — stated limitation; both tails in the moving-block
  upgrade path.
- **env.excess column → I_cond,LB** (the conditional-information
  certificate in nats: seismic .041 bold; mag/xray .001; else 0).
- Cor |r|; abstract "model-calibrated ... conditional"; conclusion
  violations line replaced; §6.1 retitled "Beyond polyhedral objectives:
  contact-order response"; 3 CR-corrupted \ref{thm:contact/incr} repaired
  (the \r escape gotcha — same class as the tab-frac and endtabular bugs:
  ALWAYS chr(92) in python edit scripts).
Remaining for submission build: dependence-aware intervals (moving-block),
both tails resolved, lit-check verdicts (2:17am cron), drop version line.

## Lit check (2026-07-22 ~23:00, WebSearch inline — agents still limited)

1. **Thm 2 folklore status: PARTIALLY KNOWN, exact form not surfaced.**
   Adjacent classical families: MI<->Bayes-error (Fano/Feder–Merhav;
   "Bayesian Error Based Sequences of MI Bounds" arXiv:1409.6654),
   MI<->variation (Pinsker line), regret-information (Russo–Van Roy;
   "On Bits and Bandits" arXiv:2405.16581). No verbatim
   Delta <= Omega*sqrt(I/2) for bounded objectives found. Paper now says
   so explicitly ("we claim assembly and anchoring, not the inequality").
2. **Hinge vs econ: phenomenon known, form not.** Radner–Stiglitz 1984 ✓;
   **Chade–Schlee JET 107(2):421–452, 2002** (general sufficient
   conditions for the nonconcavity) verified and now cited at both
   Radner–Stiglitz mentions. Exact covariance-parametrized hinge for
   delayed binary sensing: not surfaced. (Also noted: Whitmeyer
   arXiv:2404.01190 — not cited, could be for submission.)
3. **Citation corrections:** soleymani22 authors = Soleymani, Baras,
   HIRCHE (Johansson only in the 2023 Global Optimality follow-up) —
   FIXED. ayan19 ICCPS 2019 ✓ verified. NEW cite: Soleymani–Baras–
   Johansson, "Relation between value and age of information in feedback
   control," arXiv:2403.11926 (2024) — directly the value-age relation,
   added to the AoI-critics paragraph.
4. AoI x MI at sensing lag: nothing found bounding decision value by MI
   at the lag — the niche looks open.

## Battery v5 + v5b (2026-07-23 ~00:30) — the upgrade path EXECUTED

v5 (M=299, both tails): eps_under ~ 0 or negative on most series -> v4
equivalence labels were conservative; under two-tail U2, VAD and whale
become class-EQUIVALENT; protons stays just above margin (.032).
v5b (valid conservative pairing): k=6 CV policy vs pooled-EXACT
single-sample policy, moving-block bootstrap within runs at D*.
- VALIDITY CATCH: the naive k6-vs-k1(CV) pairing OVERSTATES incremental
  value (k1-CV underperforms exact V1) — Markov ref exposed it with a
  phantom certificate; v5b's exact-arm pairing removes it (ref CI
  straddles 0 ✓, azimuth slightly negative ✓).
- SELECTION-BIAS FLOOR: iid null's paired CI [+.005,+.020] positive —
  D* is an argmax; bootstrap doesn't cover lag selection (reviewer's
  caveat, empirically visible). Certificates claimed only above the
  ~0.02 floor: seismic (0.1456 >>) and magnetometer (0.022, marginal).
- HEADLINE: seismic I_cond >= 0.0424 nats dependence-aware vs 0.041
  model-calibrated — two independent routes agree to 3%.
Paper v0.7: protocol upgraded ("executed" replaces "upgrade path"),
results reading 4 dual-certificate, artifacts archived
(battery_v5*.json/py).

## Review round 4 (2026-07-23 ~01:00) — submission-ready bar; v0.8

1. Remark dead-zone: BOTH branch thresholds (negative branch larger by
   (1−π)/π for rare events — consequential, now stated).
2. "symmetric kink set" → reflection symmetry of the value function
   (locations AND slope jumps).
3. Abstract/intro: "quadratic to leading order" (exactly only for squared
   error). 4. Conclusion: sign-dependent hinges under polyhedral +
   smooth-quadratic. 5. "unique" → "the polyhedral configuration
   yielding threshold-free linear response". 6. Boundary-of-exactness:
   "principal tractable regime", not "precisely". 7. Preview window
   off-by-one: [t−m, t−D−1].
- Certification language: block-bootstrap = PRIMARY (seismic
  I_cond ≥ 2(.146)² ≈ .043 nats, selection caveat stated, floor dwarfed
  7x); surrogate route = corroborating model-based calibration (.041);
  "two complementary" not "independent"; magnetometer = exploratory.
- CONSOLIDATED ON v5: Table 2 rebuilt (π̂, gain, p, ε_over, ε_under, U₂,
  paired CI, verdict); upgrade-path narrative removed from protocol;
  v3/v4 history → repository record. Control-char corruption fixed
  (\v → VT, \a → BEL — the arepsilon/pprox artifacts). Title: "Age-Limited
  Decisions". Selection-inside-bootstrap = registered camera-ready
  refinement.
Reviewer: "after those changes, genuinely submission-ready."

## Review round 5 + selection-aware execution (2026-07-23 ~02:00) — v0.9

THE FINAL STATISTICAL OPERATION EXECUTED (v5c): lag selection repeated
inside every block-bootstrap replicate (shared block starts across lags,
max re-selected per replicate, bound from the max-statistic distribution).
- BUG CAUGHT ON FIRST RUN: 64-fraction cap truncated block coverage for
  large-n domains (seismic mean shrunk ~20x, 0.157->0.0098 — impossible
  numbers exposed it); fixed with kk_max-sized draws.
- RESULT: seismic selL05 = +0.1453 -> I_cond >= 0.042 nats,
  dependence- AND selection-aware — survives, as the reviewer predicted.
  THREE routes agree 0.041-0.042. Markov ref ~0 ✓; iid residual optimism
  +0.008 (2.5x better than fixed-D* floor); claims gated on the detection
  test (excludes whale's winner's-curse +0.040 at p=1.0, protons p=.11);
  magnetometer exploratory (0.001 nats).
Cleanup: U2/eps_under notation unified; I_cond uses eps_over; window-
witness calibration caveat; abstract/C6 precise counts (four equivalent,
one noise-limited, two at/below floor, one material); O(r^2) ->
"illustrates ... consistency illustration" (same-table caveat); certify
language scoped (theorem exact; empirical = calibrated/dependence-aware/
selection-aware as earned); paired-CI column relabelled "at fixed D*";
VAD [0,0] explained (identical policies at D*=1); MI bias O(1/N);
Table 1 float [!ht]; conclusion wording. Title: Age-Limited Decisions.
Reviewer bottom line round 5: "With those changes, ready to submit."
