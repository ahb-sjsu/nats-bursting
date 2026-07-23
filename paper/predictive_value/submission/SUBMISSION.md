# Submission build — ACM SIGMETRICS 2027 (POMACS)

**Venue rationale.** The contribution is theory + measurement in equal
halves (eight results anchored to an exact systems law; a nine-series
battery with equivalence testing and a selection-aware bootstrap bound).
SIGMETRICS/POMACS is the community whose aesthetic this matches ("simple
law, carefully validated" — the same assessment given the companion
paper), hosts the AoI literature the paper engages, and its journal
format fits the paper without amputation. Rejected alternatives: ISIT
(5pp — would cut the battery, half the contribution), IEEE T-IT
(theory-only culture; Thm 2 is deliberately elementary there),
ITW/Allerton (visibility).

**CFP facts (verified 2026-07-23,
sigmetrics.org/sigmetrics2027/pages/cfp.html):**

| cycle | abstract | paper | notification |
|---|---|---|---|
| Summer | Jul 3, 2026 | Jul 10, 2026 | passed |
| **Fall (TARGET)** | **Oct 2, 2026** | **Oct 9, 2026 (AoE)** | Dec 9, 2026 |
| Winter (backup) | Jan 4, 2027 | Jan 11, 2027 | Mar 10, 2027 |

Page limit: **20 pp single-column acmsmall technical content** (tables
and figures included) + unlimited references + unconstrained correctness
appendix. Format `\documentclass[acmsmall, screen, review]{acmart}`, no
margin/font changes; **double-anonymous** (our `anonymous` option
implements it); **reproducibility declaration required at submission**.
Current build: **14 pp total incl. appendix + refs — compliant, ~6 pp
headroom.**

**This build** (`sigmetrics.tex`): generated from `../main.tex` by
scripted transform — acmart preamble; abstract reordered into acmart
topmatter; anonymized (author block; "our companion" → "a companion
systems submission"; companion bib entry → Anonymous, with the note that
all cited results are restated with proofs in the appendix); draft
dateline dropped; `remark` environment added via `\AtBeginDocument`.
Compiles clean, zero undefined references.

**Checklist before upload (Fall cycle)**
- [ ] Use the headroom: hinge sign-branch figure, O(r²) tightness-curve
      figure, battery overview figure (reviewer-suggested, optional).
- [ ] Reproducibility declaration paragraph: battery drivers v4/v5/v5b/v5c
      + result JSONs + state-preparation scripts; anonymized hosting for
      review, public repo at camera-ready.
- [ ] Submit the companion to INFOCOM first (~Jul 31, 2026) so the
      anonymized "under review" reference is literally accurate.
- [ ] Optional cite: Whitmeyer, arXiv:2404.01190 (VoI (con-)cavity).
- [ ] Camera-ready-only: de-anonymize; restore companion citation; ACM
      rights block; CCS concepts; final keywords.
