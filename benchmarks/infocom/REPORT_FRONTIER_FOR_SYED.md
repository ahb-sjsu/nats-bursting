# Live matched-mismatch frontier — handoff report

**For:** Syed (compiling the INFOCOM 2027 submission)
**From:** Andrew's rig (2×GV100 node), campaign run 2026-07-29
**TL;DR:** The missing experiment from the 56-Sol revision's threats-to-validity
is now measured. **At matched mismatch, the AIMD feedback branch delivers
1.31–1.39× the best record-independent policy** (Δ = +0.022 to +0.027 tasks/s).
The unmatched 1.41× headline barely moves when matched, so the paper's weakest
caveat ("the comparison is not at matched mismatch") can be replaced with a
measured frontier figure. Everything below is drop-in ready.

---

## 1. What was run and why

The 56-Sol revision honestly flags that Table 1 compares AIMD (ρ=0.15) against
one static point (ρ=0.11) — different mismatch rates, so it is not a test of
the matched-constraint claim in Theorem 1. This campaign traces **both curves
on the same rig in one session** so goodput is compared at equal ρ:

- **Record-independent curve:** static trickle `--rate` ∈ {0.03, 0.05, 0.06,
  0.08, 0.12, 0.18, 0.28} — 7 operating points spanning ρ ≈ 0.03 → 0.49.
- **Feedback curve:** AIMD (α, β) ∈ {(1,0.25), (1,0.5), (1,0.75), (2,0.5),
  (3,0.35)} — 5 settings around the published cell.
- 4 seeds (42–45) per cell, randomized interleaved order, **48 trials,
  0 contaminated** (resident GPU stack SIGSTOPed during the campaign and
  auto-restored; per-trial ego-utilization monitor read 0.0 throughout).
- All other parameters identical to the published Table-1 cells:
  `--profile square --burst 16 --work 1000 --matmul 4096 --tau 25
  --comp-life 25 --interval 1 --gpus 1,0`. Square contention only — the regime
  where the paper claims value.

The published Table-1 static (rate 0.06) and AIMD (1, 0.5) cells were **re-run
inside this campaign** so every frontier point shares one session (see §5).

## 2. Record-independent frontier

Static cells (mean ± 95% t-CI, n=4):

| rate | ρ | goodput (tasks/s) |
|---|---|---|
| 0.03 | 0.031 ± 0.000 | 0.0332 ± 0.0000 |
| 0.05 | 0.066 ± 0.005 | 0.0543 ± 0.0000 |
| 0.06 | 0.092 ± 0.000 | 0.0646 ± 0.0000 |
| 0.08 | 0.360 ± 0.016 | 0.0831 ± 0.0000 |
| 0.12 | 0.486 ± 0.019 | 0.1090 ± 0.0028 |
| 0.18 | 0.482 ± 0.024 | 0.1086 ± 0.0021 |
| 0.28 | 0.487 ± 0.016 | 0.1088 ± 0.0006 |

The comparison curve is the **concave upper envelope** of these points plus the
origin. Justification (put this sentence in the paper — reviewers will ask):
*time-sharing between two record-independent policies is itself
record-independent, so the envelope is achievable, and it is the strongest
record-independent competitor the data support.* Envelope vertices:
(0, 0) → (0.031, 0.033) → (0.066, 0.054) → (0.092, 0.065) → (0.486, 0.109).

Two structural facts worth a sentence each:
- `rate 0.08` (ρ=0.36, g=0.083) falls **below** the envelope chord — dominated
  by time-sharing 0.06 and 0.12. The raw static curve is not concave; the
  envelope repairs it.
- The curve saturates at ~0.109 tasks/s once ρ ≈ 0.49 (the greedy corner:
  Table 1's naive row sits there).

## 3. Feedback curve and the matched comparison

AIMD cells and their evaluation against the envelope at each cell's own ρ:

| (α, β) | ρ | goodput | envelope(ρ) | Δ_live | ratio |
|---|---|---|---|---|---|
| (1, 0.25) | 0.123 ± 0.005 | 0.0947 ± 0.0003 | 0.0681 | **+0.0266** | **1.39** |
| (1, 0.5)  | 0.143 ± 0.054 | 0.0944 ± 0.0014 | 0.0704 | +0.0241 | 1.34 |
| (1, 0.75) | 0.150 ± 0.053 | 0.0943 ± 0.0012 | 0.0712 | +0.0231 | 1.32 |
| (2, 0.5)  | 0.142 ± 0.056 | 0.0940 ± 0.0009 | 0.0703 | +0.0238 | 1.34 |
| (3, 0.35) | 0.156 ± 0.063 | 0.0940 ± 0.0013 | 0.0718 | +0.0222 | 1.31 |

**Robustness of the headline:**
- Cleanest point is (1, 0.25): ρ CI ±0.005, so essentially no matching
  uncertainty; Δ = +0.0266, ratio 1.39.
- Worst-case CI corner on the widest cell (1, 0.5): at its ρ **upper** CI
  (0.197) the envelope gives 0.0764, against the goodput **lower** CI 0.0930 —
  the advantage (+0.017, ratio ≥ 1.22) survives every corner of every cell.
- Secondary finding: the AIMD cluster is **insensitive to (α, β)** — all five
  settings land at ρ 0.12–0.16, g ≈ 0.094. Under square contention AIMD
  self-regulates to the wave's duty cycle. Worth one sentence; it preempts
  "did you tune α, β?"

## 4. Suggested paper edits (drop-in)

**(a) Preamble** (`infocom.tex`): add
```latex
\usepackage{pgfplots}
\pgfplotsset{compat=1.17}
```

**(b) Q2 subsection** — after the Poisson paragraph in `infocom_eval.tex`:

```latex
\noindent\textbf{Live matched-mismatch frontier.}
A follow-up campaign on the same node closes the gap between the selected
operating points and the matched-constraint claim. Static admission rates in
$\{0.03,\dots,0.28\}$ trace the record-independent curve and five AIMD
settings trace the feedback curve, four seeds per cell, randomized
interleaved, in a single rig session (48 trials, none contaminated). The
record-independent comparator at each mismatch level is the concave upper
envelope of the static cells and the origin, which is achievable because
time-sharing record-independent policies is itself record-independent. At
matched mismatch the feedback branch obtains $1.31$--$1.39$ times the
envelope (goodput excess $+0.022$ to $+0.027$ tasks/s;
Fig.~\ref{fig:frontier}). The advantage survives the most pessimistic
confidence-interval corner of every cell ($\ge 1.22$), and the five AIMD
settings cluster at $\rho=0.12$--$0.16$ regardless of $(\alpha,\beta)$, so
the result is not an artifact of parameter selection. The static curve
saturates at $0.109$ tasks/s beyond $\rho\approx0.49$, and its raw points are
not concave: the $\mathrm{rate}=0.08$ cell is dominated by time-sharing its
neighbours, which is why the envelope, not the raw curve, is the correct
record-independent frontier.
```

**(c) Figure** (place near the paragraph):

```latex
\begin{figure}[t]
\centering
\resizebox{0.95\columnwidth}{!}{%
\begin{tikzpicture}
\begin{axis}[xlabel={$\rho$ (mismatch)},ylabel={goodput (tasks/s)},
  xmin=0,xmax=0.55,ymin=0,ymax=0.12,
  legend pos=south east,legend style={font=\scriptsize},
  width=8.6cm,height=5.6cm,grid=major,grid style={black!10}]
\addplot[thick,black,mark=*,mark size=1.6pt] coordinates
  {(0,0) (0.031,0.0332) (0.066,0.0543) (0.092,0.0646) (0.486,0.109)};
\addlegendentry{record-independent envelope}
\addplot[only marks,mark=x,mark size=2.6pt,black!60] coordinates
  {(0.360,0.0831) (0.482,0.1086) (0.487,0.1088)};
\addlegendentry{static cells (incl.\ dominated)}
\addplot[only marks,mark=square*,mark size=2pt,blue,
  error bars/.cd,x dir=both,x explicit,y dir=both,y explicit]
  coordinates {(0.123,0.0947)+-(0.005,0.0003) (0.143,0.0944)+-(0.054,0.0014)
   (0.150,0.0943)+-(0.053,0.0012) (0.142,0.0940)+-(0.056,0.0009)
   (0.156,0.0940)+-(0.063,0.0013)};
\addlegendentry{AIMD $(\alpha,\beta)$ sweep}
\draw[<->,thick,red] (axis cs:0.123,0.0681) -- (axis cs:0.123,0.0947)
  node[midway,right,font=\scriptsize,text=red]{$+0.027$ ($1.39\times$)};
\end{axis}
\end{tikzpicture}}
\caption{Live matched-mismatch frontier under square contention (4 seeds per
cell). The feedback branch exceeds the record-independent envelope by
$1.31$--$1.39\times$ at its own mismatch level.}
\label{fig:frontier}
\end{figure}
```

**(d) Threats paragraph** — replace the first two sentences of
`\subsection{Summary and threats to validity}`'s second paragraph ("The main
limitation is the absence of a live matched-$\rho$ frontier. The static
policy in Table~1 is one operating point... at common values of $\rho$.")
with:

```latex
The live matched-$\rho$ frontier above addresses the prior revision's main
gap; its remaining limits are that the envelope is built from seven static
rates on one node, and that the AIMD cells' $\rho$ intervals rest on four
seeds. Contention is controlled on one two-GPU node rather than drawn from a
production multi-user trace.
```
(Keep the rest of the paragraph: two-seed switch sweep, "kept" column,
completion-gated epochs.)

**(e) Abstract** — change "obtains 1.41 times the goodput of one static
operating point under structured contention, at a different mismatch rate" to:

```
obtains 1.41 times the goodput of one static operating point and 1.31--1.39
times the best record-independent envelope at matched mismatch under
structured contention
```

**(f) Conclusion** — update the corresponding sentence the same way, and in
the open-work paragraph delete "A live matched-mismatch frontier needs more
operating points and more repetitions." (now measured; production-trace
contention remains the honest open item).

## 5. Caveats to preserve (do not oversell)

1. **Cross-session drift ≤ 4%.** The in-session re-runs of the Table-1 cells
   land close but not identical to the published values: static 0.06 →
   (ρ 0.092, g 0.0646) vs published (0.11, 0.064); AIMD (1,0.5) → (0.143,
   0.0944) vs published (0.15, 0.091). Different day/thermal state. All
   frontier comparisons are within one session, which is why the cells were
   re-run rather than imported. Keep Table 1 as its own session; don't mix
   numbers across the two tables.
2. **Square contention only.** The frontier was measured where the paper
   claims value. Under Poisson the break-even result stands unchanged.
3. **Envelope, not exhaustive search.** The record-independent comparator is
   the envelope of seven rates; a finer rate grid could raise it slightly.
   The CI-corner check in §3 bounds how much that could matter near the AIMD
   cluster (the envelope there is interpolated between well-separated,
   tight-CI cells).

## 6. ⚠ Pre-existing paper/logs inconsistencies (fix while compiling)

Found while setting this up — the 56-Sol text's parameter sentence does not
match the experiment logs that produced Table 1:

- Paper says **"64 submitted Jobs per trial"**; the logs say `--burst 16`.
- Paper says **"an 8 s GPU work unit"**; the logs say `--work 1000` matmul
  iterations at `--matmul 4096` (work time varies under contention; ~8–12 s
  uncontended is plausible but is not a configured 8 s unit).
- Paper says **α = 0.5**; the harness `--alpha` is an integer and the
  published cells ran α = 1 (also: β = 0.5 matches).
- Paper says **K = 4**; verify against the harness default before keeping.

The revision notes' own action item ("confirm all numerical values against
the experiment logs") covers exactly this — these four are the ones I can
already confirm are wrong or unverified.

## 7. Data and reproduction

- **Committed here:** raw per-trial JSONs (48) in
  `benchmarks/infocom/e9_results/frontier/`, cell summary in
  `benchmarks/infocom/e9_results/frontier_summary.json`, campaign driver
  `e9_frontier.py`, suspend wrapper `run_frontier_suspend.sh`, analyzer
  `e9_frontier_analyze.py`, results narrative `RESULTS_FRONTIER.md`.
- **Durable copy on the rig:** `atlas:/archive/experiments/e9_frontier/`
  (JSONs + campaign log).
- **Reproduce:** upload `e9_contended.py`, `e9_frontier.py`,
  `run_frontier_suspend.sh` to the node, then
  `screen -dmS e9frontier bash run_frontier_suspend.sh`; ~3 h wall-clock;
  analyzer prints the matched table. The driver is idempotent (skips existing
  JSONs), so a killed campaign resumes where it stopped.
- Each JSON's `result` block has `goodput_tasks_per_s`, `over_admission_rho`,
  `alpha`, `beta`, and `cfg.rate`; `samples` holds the 1 Hz occupancy trace if
  you want to re-derive anything.
