# Symbolic checks of "The Value of Delayed Information"

MATLAB Symbolic Math Toolbox scripts (run with R2026a). Run headless: `matlab -batch "run('t1_tightness.m')"`.

| script | paper result |
|---|---|
| `t1_tightness.m` | Proposition 3.5: series of I(r), the sqrt(I/2) ratio, O(r^3) gap, I >= r^2/2 |
| `t2_series.m` | Proposition 5.2(i): all series coefficients of I(r) positive |
| `t3_preview.m` | Proposition 5.2(ii): preview-process mutual information and value |
| `t4_hinge.m` | Theorem 6.1: hinge branches and worked examples |
| `t5_quadratic_contact.m` | Proposition 6.2 and Theorem 6.3 |
| `t6_layercake.m` | the layer-cake decomposition against the matched-surplus benchmark |
| `t7_bits_beta.m` | Corollary 3.2 threshold and beta(D) = abs(r)/2 |
