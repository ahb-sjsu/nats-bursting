# Registration: BGP series and block-stationarity check

Paper: `submission/sigmetrics.tex`, Section "The law and its envelopes across
domains" (the battery). Registered 2026-09-30, BEFORE any BGP data was
fetched or inspected. The git commit that adds this file alone is the
registration timestamp. Nothing below is tuned after seeing results; any
deviation forced by the data is reported as a deviation, with its reason.

Compute: Atlas, `/archive/infocom_battery/bgp_stat/` (new directory; no
existing file in `/archive/infocom_battery/` is modified). CPU only, joblib
`n_jobs=8` (thermal limit; the original runs used 20, which changes only
wall time, not results, because every random draw is seeded per task).

## (a) The BGP series

**Collector.** RIPE RIS `rrc06`. Fallback, used only if more than 50% of
the window's update files are unavailable from rrc06: `rrc00`, same window,
same everything else (reported as a deviation if used).

**Window.** 2026-09-01 00:00:00 UTC (inclusive) to 2026-09-08 00:00:00 UTC
(exclusive): 10,080 one-minute bins, minute index
`t = floor((ts - 1788220800) / 60)`, `t in [0, 10080)`.

**Files.** `https://data.ris.ripe.net/rrc06/2026.09/updates.YYYYMMDD.HHMM.gz`,
5-minute files, nominal 2026-09-01 00:00 through 2026-09-07 23:55 (2,016
files). Because MRT records near a file boundary can carry timestamps of the
adjacent interval, the neighbouring files `updates.20260831.2355.gz` and
`updates.20260908.0000.gz` are also read, and only records with timestamps
inside the window are counted, wherever they come from. Files are streamed
(downloaded, parsed, deleted); only per-minute counts are kept.

**Count.** For each minute, the number of BGP update elements of type
announcement (`A`) or withdrawal (`W`) emitted by the bgpkit parser
(`pybgpkit`, module `bgpkit`) over all peers and all prefixes whose
timestamp falls in that minute. One element is one prefix announced or
withdrawn in one UPDATE message from one peer, so this is "announcements +
withdrawals, all peers, all prefixes". (Counting raw UPDATE message
envelopes is not exposed by the Python parser; the element count is the
registered quantity.) BGP4MP state-change records are not counted.

**Missing data.** A minute is *missing* if the nominal 5-minute file whose
interval contains it is absent (HTTP error after 3 attempts) or fails to
parse. Missing minutes are always excluded, never zero-filled, whatever
their number; the number and fraction of missing files are reported, and
the fraction is flagged if it exceeds 1%. Excluded minutes split the series
into separate runs. The series is stored, as the existing loaders expect, as
a list of `int8` runs (contiguous observed minutes). The existing code
already handles multiple runs: lag tables pool pairs within runs only;
blocked cross-validation folds within each run and skips runs shorter than
`5*(D+k+5)`; surrogates are fitted and generated per run; moving blocks are
drawn within runs. With no missing minute the series is a single run,
exactly like the existing `*_v2.npy` series (`C.npy` returns `[array]`).

**State.** `X_t = 1` if the minute-`t` count exceeds the median of the
per-minute counts over all observed minutes of the window, else `0` (ties
to 0). One global threshold over the window. (Note: the existing GOES and
seismic `_v2` series use a rolling-median local-anomaly threshold,
`prep_v2.py`; the BGP series uses the global window median as registered
here; both are threshold binarizations fixed before analysis.)

**Cadence and lags.** 1/60 Hz. Lag grid `C.flags(90)` (lags 1, 3, ..., 45,
46, 49, ..., 88: 38 lags), exactly as the GOES X-ray, GOES magnetometer and
seismic entries of `battery_v4.py`/`battery_v5.py`. History class `k=6`
lookup (`C.K`), 5-fold contiguous blocked CV.

**Runs and settings.** One series, one analysis run per driver, with
drivers copied from `battery_v4.py`, `battery_v5.py`, `battery_v5b.py`,
`battery_v5c.py` and changed only in: the import path, `n_jobs`, the domain
list (BGP only), input/output paths. Same `M_SURR=299` (seeds 9000+s),
`FLOOR=0.03`, `N_BOOT=2000`, block length `max(10, 2*D*)`, v5c grid = every
second registered lag plus `D*`, bootstrap seed 0. Outputs `bgp_v4.json`,
`bgp_v5.json`, `bgp_v5b.json`, `bgp_v5c.json`.

**Known defect in the released v5c script, and the registered repair.** The
released `battery_v5c.py` draws `fracs = rng.random(64)` per replicate, the
64-fraction cap that NOTES.md records as a bug caught on the first run
("fixed with kk_max-sized draws"). The fixed script that produced the
paper's `battery_v5c.json` is not preserved. The registered repair draws
`fracs = rng.random(kk_max)` per replicate, `kk_max` = the maximum over all
grid lags and runs of `ceil(n / L)`. Before the BGP run, the repaired script
is run on the existing seismic (and if fast, X-ray) series to check that it
reproduces the paper's `battery_v5c.json` values. Whether it reproduces
exactly, approximately, or not at all is reported; the repaired script is
used for all v5c quantities here either way.

**Decision rules (the paper's, applied unchanged).**
- Detection: the parametric-bootstrap `p` is at its floor, `p = 1/300`
  (written `<.004`). Detection takes precedence over equivalence.
- Not detected and `U2 = gain_max + eps_under < 0.03`: "equivalent" (no
  additional value detected by the registered six-lag lookup policy,
  equivalent within the margin).
- Not detected and `U2 >= 0.03`: "not established".
- Detected and `gain_max < 0.03`: "detected, below floor".
- Detected, `gain_max >= 0.03`, but a moving-block lower bound
  (`L_D*` from v5b or `L_max = sel_L05` from v5c) below 0.03: "detected
  (exploratory)".
- Detected with both moving-block lower bounds above 0.03: "history adds";
  certificate `max_D I(X_t; history_D | X_{t-D}) >= 2 (sel_L05)^2` nats,
  issued only when detected. Paired lower bounds are claimed only above the
  selection floor (~0.02) the paper states.
- Tightness ratio: if `|pi_hat - 1/2| < 0.035`, report the v4
  `med_env_over_v1` (median of `sqrt(I/2)/V1` over lags with `|r| > 0.05`),
  the quantity behind the paper's "1.11 to 1.35".

## (b) Block-stationarity check

**Series.** Seismic ANMO (`seismic_v2`), GOES X-ray flux (`xray_v2`), GOES
magnetometer (`mag_v2`), GOES protons (`protons_v2`), and the new BGP
series. Binary states are taken as already binarized for the full series;
they are NOT re-thresholded per block.

**Blocks.** Three equal contiguous blocks (thirds). For the four existing
series, which are single runs without stored timestamps, the thirds are by
sample index (`np.array_split(x, 3)`), which equals calendar thirds to the
extent the series is regularly sampled. For BGP, the thirds are calendar
thirds of the window (minutes [0, 3360), [3360, 6720), [6720, 10080)),
with missing minutes excluded and runs split inside each block as above.

**Per block, report.**
- `pi_hat` (fraction of ones) and lag-1 transition probabilities
  `P(1|0)`, `P(1|1)` (pooled within runs);
- the v5 quantities, recomputed on the block alone with the series' own
  full-series lag grid and the v5 code path (M=299, seeds 9000+s):
  `max_gain` over exact `V1`, `p`, `eps_over`, `eps_under`, `U2`, `D*`;
- the v5c selection-aware lower bound `sel_L05` (repaired v5c code; grid =
  every second lag plus the block's own `D*`; N_BOOT=2000, seed 0), and,
  where the block is detected (p at floor), the implied certificate
  `2[(sel_L05)^+]^2`.

**Pre-stated reading.** The seismic certificate is "block-robust" if
`sel_L05 > 0.03` (the practical floor) in all three seismic blocks;
otherwise the failing blocks are named and the certificate is reported as
not block-robust. For the other series, the per-block verdicts under the
rules in (a) are reported without a robustness claim.

**Homogeneity diagnostic (no decision depends on it).** Per series, a
chi-square test that the three blocks share one lag-1 transition matrix
(Anderson-Goodman): for each previous state `i in {0,1}`, the 3x2 table
blocks x next-state, Pearson chi-square, summed over `i`; df = 4; report the
statistic, df and asymptotic `p`.

Output: `stationarity.json` (script `stationarity_blocks.py`, reusing the
functions of the copied v5 and v5c drivers). All new scripts and JSON
outputs are copied to `paper/predictive_value/bgp_stat/` (not committed).
