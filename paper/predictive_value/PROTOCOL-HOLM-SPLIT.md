# Registration: Holm detection rule, larger surrogate sets, selection/evaluation split

Paper: `submission/sigmetrics.tex`, Section "The law and its envelopes across
domains". Registered 2026-10-07, after the v5, v5b, v5c, BGP and block results
were known, in response to a review that raised two points: (1) the detection
rule ("p at its Monte Carlo floor") was adopted during the final analysis, and
(2) the selection-aware lower bound has no formal coverage argument. The git
commit that adds this file, together with the three scripts it names and
before any of them is run, is the registration timestamp. Nothing below is
tuned after seeing the new results; any deviation is reported with its reason.

Compute: Atlas, new directory `/archive/infocom_battery/holm_split/`. No
existing file in `/archive/infocom_battery/` is modified. Copies of
`boundary_map.py`, `calibrate_par.py` (both identical to the copies in
`bgp_stat/`, md5 checked) and `bgp_series.py`, plus the released
`battery_v5.py`, are imported from that directory. CPU only, joblib `n_jobs=8`
per script, at most two scripts at once (thermal limit 20 workers).

## (1) Detection rule

**Rule.** A series is *detected* if Holm's step-down procedure rejects its
null at one-sided family-wise level alpha = 0.05. The p-value is the
parametric-bootstrap p under the fitted Markov null, `p = (1 + #{T_j >= T_obs}) / (M + 1)`,
with the statistic, surrogate generator and lag grid of `battery_v5.py`
unchanged.

**Families.** Main battery: the ten series of the battery table (two-state
Markov, i.i.d. null, LOCATA azimuth, LOCATA VAD, sperm-whale codas, GOES
X-ray, GOES magnetometer, GOES protons, seismic ANMO, BGP rrc06). Controls are
included in the family, which can only make the rule stricter. Calendar-block
analysis: the fifteen block tests (five series, three blocks each), one family.

**Surrogates.** `M = 4999`, seeds `9000 + s`, `s = 0..4998`, for every test in
both families. The first 299 seeds are the original ones.

**Guards (reproduction).** For every test the script recomputes the observed
maximum gain and the surrogate count over the first 299 seeds. The gain must
equal the stored v5 (or block) value to 1e-12, and the count must equal
`round(300 p_old - 1)`. A test failing either guard is reported as a deviation
and its new p is not used.

**What changes in the paper.** Only the p-values and the detection column.
The verdict definitions are otherwise unchanged, with "detected" now meaning
Holm rejection. The calibration tails (eps_over, eps_under), U2 and the
model-calibrated certificate stay those of the registered M = 299 calibration;
the M = 4999 tails are written to the result file and any verdict they would
change is reported in the artifact. If Holm at M = 4999 changes the detection
set of either family, the paper reports the new set and the verdicts it
implies.

Script: `holm_split/surr_large.py main` and `holm_split/surr_large.py blocks`.
Outputs: `surr_main.json`, `surr_blocks.json` (p at M = 4999, the guard
values, the M = 4999 tails, Holm decisions with their thresholds).

## (2) Selection/evaluation split

**Purpose.** A lower bound at a lag chosen on data the bound never sees, so the
one-sided moving-block bootstrap has its standard coverage conditional on the
selected lag.

**Split.** Single-run series (Markov, i.i.d., GOES X-ray, magnetometer,
protons, seismic, BGP): the run is cut into 4 equal contiguous chunks
(`np.array_split`); chunks 0 and 2 form the selection set, chunks 1 and 3 the
evaluation set. Multi-run series (LOCATA azimuth and VAD, 8 runs each; whale
codas, 20 runs): whole runs alternate in loader order, even index to
selection, odd to evaluation. Lag pairs never cross a chunk or run boundary.
The run structure (counts and lengths only) was inspected before this choice;
no outcome on either half was computed.

**Selection.** On the selection set only: for every lag of the series'
registered grid (the v5 grid), gain(D) = 5-fold blocked-CV value of the k=6
lookup minus the exact plug-in single-sample value, exactly as in
`battery_v5.py`. D*_sel = argmax. The k=6 lookup table at D*_sel is then
trained on the whole selection set (`boundary_map.train_lookup`).

**Evaluation.** On the evaluation set only, at the frozen D*_sel: per position,
d_t = correct(k=6 table from the selection set) - correct(exact single-sample
policy fitted in-sample on the evaluation set), the conservative pairing of
`battery_v5b.py` (the in-sample fit favours the single-sample arm). One-sided
95% moving-block bootstrap of the mean of d: blocks within chunks or runs,
block length `max(10, 2 D*_sel)`, `N_BOOT = 2000`, seed 0. L_split = 5th
percentile. Certificate `2 [(L_split)^+]^2` nats, a statement at the fixed lag
D*_sel about the evaluation-half mixture.

**Reported for all ten series, whatever the result:** D*_sel (and the full-data
D*), the evaluation mean of d, L_split, the certificate. The paper states
L_split and the certificate for every Holm-detected series, and says whether
each clears the practical floor 0.03. If a detected series' L_split falls below
the floor or below zero, the paper says so.

Script: `holm_split/split_eval.py`. Output: `split.json`.
