# Revision notes

This revision addresses the major issues identified in the prior review without
inventing new experimental results.

## Corrected in the manuscript

- Removed every claim about a second multi-unit algorithm.
- Replaced `sensing age` with `observation-to-effect lag` and separated record age
  from launch-to-effect delay.
- Narrowed the delay proposition to the measured launch-on-demand path. The paper
  now acknowledges warm pools and pipelining as alternative designs.
- Defined over-admission as a capacity-mismatch proxy rather than a direct host
  policy violation.
- Corrected the NRP policy framing and added the current policy-page citation.
- Removed dependence on anonymous companion manuscripts and author-only artifact
  citations.
- Made Algorithm 1 explicit about its capacity sample, delayed outcome, estimator
  projection, real-valued target, integer execution and branch comparator.
- Recast the learning theorem as a local branch-selection result with an explicit
  crossing assumption. It no longer claims that AIMD reaches the optimal
  threshold frontier.
- Replaced the invalid uniform asymptotic expression with the exact finite-D
  sensitivity and a separately qualified large-D approximation.
- Recast the general-capacity appendix as a scalarized mixing bound rather than a
  general constrained-frontier theorem.
- Rewrote the evaluation so the live 1.41x result is clearly an unmatched
  operating-point comparison. The two-seed live sweep is described only as a
  mechanical switch check.
- Removed author information from the source and PDF metadata.

## Remaining author actions

- Verify that the implementation uses the integer rounding rule stated around
  Algorithm 1, or edit the paper and code so they agree.
- A live matched-mismatch frontier and more repetitions would materially improve
  the submission. No such data were fabricated in this revision.
- Confirm all numerical values against the experiment logs before submission.
- Insert the real camera-ready author block only after review.
