# INFOCOM 2027 submission — manifest

**Title.** Polite Bursting: Feedback-Controlled Admission for AI Workloads over a
Federated Messaging Fabric on Shared Clusters
**Venue.** IEEE INFOCOM 2027 (Honolulu). Abstract ~Jul 24 2026, full paper ~Jul 31
2026 — *confirm against the live CFP before submitting.*
**Authors.** Andrew H. Bond (San Jose State University).

## Source & build
- Main: `paper/infocom.tex` (IEEEtran, `conference`), which `\input`s
  `paper/infocom_model.tex` (§3–4: model + AIMD/Kalman controllers, Prop. 1–2) and
  `paper/infocom_eval.tex` (§8: evaluation).
- Bib: `paper/paper.bib` (15 entries). Figures: `paper/figures/pareto_{gpu,cpu}.pdf`
  (regenerate via `paper/figures/make_infocom_figs.py`) + an inline TikZ architecture diagram.
- Build: `pdflatex infocom && bibtex infocom && pdflatex infocom && pdflatex infocom`.
- Output: `paper/infocom.pdf` — **5 pages**, compiles clean (0 errors, 0 overfull
  hboxes, 0 undefined references; all 15 citations resolve).

## Contributions
1. AIMD politeness/admission controller with a hard-cap safety guarantee and a
   steady-state over-admission bound whose dominant term is the *measured* prober
   detection delay (Prop. 1–2).
2. Federated NATS leaf-node control plane, characterized by measurement (E1–E5).
3. Transport (turboquant-pro) + Kalman-filtered thermal right-sizing (batch-probe).
4. Evaluation: system verified end-to-end on NRP Nautilus; on a controlled testbed
   the admission controller is the polite-efficient frontier point —
   **1.72× (GPU, C=2) / 3.18× (CPU, C=8)** a static baseline's goodput at equal
   politeness (ρ=0), matching a greedy baseline without over-admitting.

## Reproducibility
`benchmarks/infocom/` — the E1–E8 harness, `RESULTS.md` + `RESULTS_E8.md` (data +
honest scope), `E8_PREREG.md` (pre-registration), raw JSON under `out/`, and the
plotting/aggregation scripts.

## Honest scope (kept in the paper)
The system path is verified live on NRP; the goodput comparison ran on a controlled
node because in-situ NRP measurement was dominated by exogenous scheduling and
cold-image-pull variance (reported as three pre-registered nulls, not suppressed).
E2 (single-port tax) and E6 (partition) remain future work.

## Status
Assembled and compiling; **DRAFT pending final author review** before submission.
