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
