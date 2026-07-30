# INFOCOM submission bundle

The main document is `infocom.tex`. It inputs `infocom_aoi_model.tex`,
`infocom_eval.tex`, and `infocom_appendix.tex`, uses `infocom.bib`, and includes
the figure in `figures/tau_sweep.png`.

## Revision status

This revision removes the stale second-algorithm claims, distinguishes record age
from observation-to-effect lag, narrows the launch-delay proposition to the
measured launch-on-demand path, defines capacity mismatch as a model proxy rather
than a host-policy violation, and makes Algorithm 1 executable with an explicit
resolved outcome and integer rounding rule.

The branch-selection theorem now states its crossing assumption, compares only
the supplied feedback and static branches, retains the exact finite-D
sensitivity, and limits the simplified expression to fixed switch level as D
grows. The general-capacity appendix is explicitly a scalarized mixing bound, not
a claim of the same constrained frontier.

The evaluation language now distinguishes selected live operating points from the
matched-mismatch Markov test. It does not claim that the live 1.41x comparison is
at matched mismatch, and it reports the two-seed hardware sweep only as a
mechanical switch check.

## Double blind

`\blindtrue` produces the anonymous submission PDF and clears PDF metadata.
The source contains no author name. For a camera-ready version, insert the real
author block in `infocom.tex` and then change `\blindtrue` to `\blindfalse`.

The paper does not cite anonymous companion manuscripts or author-only software
entries. An artifact may still be submitted separately under the conference
artifact rules.

## Build

Use pdfLaTeX and BibTeX on Overleaf. The local environment used `bibtexu`, which
is BibTeX compatible.

Typical build sequence

1. `pdflatex infocom.tex`
2. `bibtex infocom`
3. `pdflatex infocom.tex`
4. `pdflatex infocom.tex`

The compiled revision is 8 pages total, including references.

## Author checks before submission

1. Confirm that the implementation really uses the integer execution rule stated
   around Algorithm 1. If it uses a different rounding rule, change the paper or
   the implementation so they agree.
2. Confirm that the term `capacity mismatch` matches the recorded metric in the
   experimental analyzer.
3. Add a live matched-mismatch frontier and additional repetitions if those data
   become available. The present paper states their absence explicitly.
4. Verify the current INFOCOM template and submission rules immediately before
   upload.
