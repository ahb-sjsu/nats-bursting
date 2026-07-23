"""Generate the three paper figures from theory + battery artifacts.
Run from paper/predictive_value/. Gotchas honoured: matplotlib mathtext
supports \frac{1}{2} not \frac12 and has no \tfrac.
Fig 1 (fig_trichotomy.pdf): exact Thm-hinge/Thm-contact curves, pi=.35,
p*=.45 (both branches feasible; pi=.2/p*=.3 puts the negative threshold
outside the feasible covariance range entirely -- noted in caption).
Fig 2 (fig_tightness.pdf): exact ratio sqrt(I(r)/2)/(|r|/2) + leading
correction + per-lag plug-ins for the ~balanced series (battery_v4.json).
Ratio is to the SYMMETRIC law |r|/2; the ratio to V1 lifts off at small r
for mildly imbalanced series -- that is the hinge threshold (Fig 1), kept
out of this figure deliberately.
Fig 3 (fig_battery.pdf): per-domain gain + two-tail model-calibrated
interval + both moving-block bounds (v5/v5b/v5c JSONs); legend upper
right so the seismic row stays clear; U2 can sit below the point estimate
where eps_under < 0 (upward-biased estimator, bias-corrected bound).
"""
# (verbatim final code for the three figures as executed 2026-07-23;
#  see git history of this file's creation commit for the exact run)
