# INFOCOM 2027 submission — manifest

**Title.** Polite Bursting: Feedback Admission Control under Age-Limited Sensing on
Shared Clusters
**Venue.** IEEE INFOCOM 2027 (Honolulu). Abstract ~Jul 24 2026, full paper ~Jul 31
2026 — *confirm against the live CFP before submitting.*
**Authors.** Andrew H. Bond (San Jose State University). Double-blind: `\blindtrue`.

## Source & build
- Main: `paper/infocom.tex` (IEEEtran, `conference`), which `\input`s
  `paper/infocom_aoi_model.tex` (System model + feedback-usefulness limit +
  regime-adaptive controller), `paper/infocom_eval.tex` (evaluation, Q1–Q4), and
  `paper/infocom_appendix.tex` (App. A β-mixing impossibility, App. B regret proof).
- Bib: `paper/infocom.bib`. Figures: `paper/figures/pareto_{gpu,cpu}.pdf`,
  `pareto_contended_{square,poisson}.pdf`, `tau_sweep.pdf` (regenerate the last via
  `benchmarks/infocom/tau_sweep.py`) + an inline TikZ architecture diagram.
- Build: `pdflatex infocom && bibtex infocom && pdflatex infocom && pdflatex infocom`.
- Output: `paper/infocom.pdf` — **8 pages** (incl. 2 appendices), compiles clean
  (0 errors, 0 undefined references, all citations resolve).

## Contributions (disjoint from the CANOPIE companion — see below)
1. **Age-of-information formulation** of polite bursting and a **feedback-usefulness
   limit**: the advantage of any causal age-$D$ admission controller over the best
   static budget is exactly $\Delta(D)=\tfrac12 r(D)$ (Thm. 1), an impossibility once
   $D>\tau_c$ (Cor.), lifted to any pod cap by a layer-cake reduction (Prop.). General
   non-binary capacity is bounded by the process's $\beta$-mixing coefficient (App. A).
2. **Regime-adaptive controller** that estimates $\tau_c$ online and switches
   closed/open-loop, tracking the limit uniformly with a hard-cap safety guarantee;
   regret $O(D\sqrt{\log N/(\gamma N)})$ via spectral-gap concentration (App. B).
3. **Evaluation**: detection delay $D\approx2.5$s (measured); abundance Pareto
   ($1.7$–$3.2\times$ static's goodput at $\rho{=}0$); real-contention frontier
   (structured knee + honest memoryless null); and controller-level validation of the
   law (optimal policy on $\tfrac12 r(D)$ to within $0.013$; AIMD < static when
   $\tau_c\lesssim D$; adaptive never below static).

## Orthogonality (submit alongside the CANOPIE-HPC systems paper)
The two papers are deliberately **disjoint** to avoid dual-submission/self-plagiarism:
- **INFOCOM owns** the admission-control theory + controller + its evaluation.
- **CANOPIE (`paper_sc26_revised.tex`) owns** the bursting fabric (NATS leaf
  federation, pools), transport compression, thermal right-sizing, and the systems
  measurements (compression, transport, cold-start/warm-pool/scaling, frameworks
  positioning). Its admission section is demoted to a rule-based deployment gate + a
  pointer to this paper.
- No shared figures, no shared experiment/result numbers; each cites the other as
  `\cite{companion}` (anonymized on the INFOCOM side).

## Reproducibility
`benchmarks/infocom/` — the contention harness (`contention.py`, incl. the new
`markov` profile for a $\tau_c$ sweep), the abundance/contention runners, and
`tau_sweep.py` (the controller-level law validation). Pre-registration in
`E8_PREREG.md`; raw JSON under `out/`.

## Honest scope (kept in the paper)
The system path is verified live on NRP; the goodput comparison ran on a controlled
node (three pre-registered in-situ nulls, reported not suppressed). The law validation
and the regime-adaptive controller are controller-level **simulation** on the
two-state process; the live NRP run of the adaptive policy is the marked next anchor.

## Status
Assembled and compiling; **DRAFT pending final author review** before submission.
Check the CFP on whether appendices count against the page limit — if so, move App.
A/B to a companion technical report and cite it.
