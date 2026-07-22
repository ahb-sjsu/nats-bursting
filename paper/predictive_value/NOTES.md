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
