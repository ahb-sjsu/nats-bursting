import Mathlib

/-!
# Binary posteriors and the hinge law (Theorem 6.1), Corollary 6.5, worked examples

Paper: `sigmetrics.tex` lines 487-548 (`thm:hinge`), figure caption 550-565,
Remark 6.4 (line 613, worked example `π = .2, p* = .3`), Corollary 6.5 (line 644),
Remark "dead zone" (line 654).

Notation: `pr` is the stationary marginal `π = P(X_t = 1) = P(X_{t-D} = 1)`,
`C` the lag covariance, `ps` a kink `p*`.
-/

open Finset

namespace PredictiveValue

/-! ## The binary joint and its posteriors -/

/-- Joint law of `(X_t, X_{t-D})` from marginal `pr` and covariance `C`:
`P(1,1), P(1,0), P(0,1), P(0,0)`. -/
noncomputable def q11 (pr C : ℝ) : ℝ := pr ^ 2 + C
noncomputable def q10 (pr C : ℝ) : ℝ := pr * (1 - pr) - C
noncomputable def q01 (pr C : ℝ) : ℝ := pr * (1 - pr) - C
noncomputable def q00 (pr C : ℝ) : ℝ := (1 - pr) ^ 2 + C

/-- Any real 2x2 table with both marginals `pr`, total mass one and covariance
`C := P(1,1) - pr^2` is exactly the table above (uniqueness). -/
theorem joint_unique (pr a b c d : ℝ) (hX : a + b = pr) (hY : a + c = pr)
    (htot : a + b + c + d = 1) :
    a = q11 pr (a - pr ^ 2) ∧ b = q10 pr (a - pr ^ 2) ∧
    c = q01 pr (a - pr ^ 2) ∧ d = q00 pr (a - pr ^ 2) := by
  unfold q11 q10 q01 q00
  refine ⟨by ring, by nlinarith, by nlinarith, by nlinarith⟩

/-- The table has the stated marginals, total mass, and covariance. -/
theorem joint_marginals (pr C : ℝ) :
    q11 pr C + q10 pr C = pr ∧ q11 pr C + q01 pr C = pr ∧
    q11 pr C + q10 pr C + q01 pr C + q00 pr C = 1 ∧
    q11 pr C - pr * pr = C := by
  unfold q11 q10 q01 q00
  refine ⟨by ring, by ring, by ring, by ring⟩

/-- Posterior after `Y = 1`. -/
noncomputable def p1 (pr C : ℝ) : ℝ := pr + C / pr
/-- Posterior after `Y = 0`. -/
noncomputable def p0 (pr C : ℝ) : ℝ := pr - C / (1 - pr)

/-- `P(X=1 | Y=1) = π + C/π`. -/
theorem posterior_one (pr C : ℝ) (h0 : 0 < pr) :
    q11 pr C / pr = p1 pr C := by
  unfold q11 p1; field_simp

/-- `P(X=1 | Y=0) = π - C/(1-π)`. -/
theorem posterior_zero (pr C : ℝ) (h1 : pr < 1) :
    q10 pr C / (1 - pr) = p0 pr C := by
  have : (1 : ℝ) - pr ≠ 0 := (sub_pos.mpr h1).ne'
  unfold q10 p0; field_simp

/-- The posteriors average back to the prior (tower property). -/
theorem posterior_mean (pr C : ℝ) (h0 : 0 < pr) (h1 : pr < 1) :
    pr * p1 pr C + (1 - pr) * p0 pr C = pr := by
  have : (1 : ℝ) - pr ≠ 0 := (sub_pos.mpr h1).ne'
  unfold p1 p0; field_simp; ring

/-- Feasible covariance range: the table is a probability table iff
`-min(π², (1-π)²) ≤ C ≤ π(1-π)`. -/
theorem feasible_iff (pr C : ℝ) :
    (0 ≤ q11 pr C ∧ 0 ≤ q10 pr C ∧ 0 ≤ q01 pr C ∧ 0 ≤ q00 pr C) ↔
    (-(min (pr ^ 2) ((1 - pr) ^ 2)) ≤ C ∧ C ≤ pr * (1 - pr)) := by
  unfold q11 q10 q01 q00
  constructor
  · rintro ⟨h1, h2, _, h4⟩
    refine ⟨?_, by linarith⟩
    rcases min_choice (pr ^ 2) ((1 - pr) ^ 2) with h | h <;> rw [h] <;> linarith
  · rintro ⟨h1, h2⟩
    have a := min_le_left (pr ^ 2) ((1 - pr) ^ 2)
    have b := min_le_right (pr ^ 2) ((1 - pr) ^ 2)
    refine ⟨by linarith, by linarith, by linarith, by linarith⟩

/-- The paper's range `[-π², π(1-π)]` (figure caption) is the feasible range
when `π ≤ 1/2` (true for the figure's `π = .35`). -/
theorem feasible_iff_of_le_half (pr C : ℝ) (hh : pr ≤ 1 / 2) :
    (0 ≤ q11 pr C ∧ 0 ≤ q10 pr C ∧ 0 ≤ q01 pr C ∧ 0 ≤ q00 pr C) ↔
    (-(pr ^ 2) ≤ C ∧ C ≤ pr * (1 - pr)) := by
  rw [feasible_iff]
  have : min (pr ^ 2) ((1 - pr) ^ 2) = pr ^ 2 := min_eq_left (by nlinarith)
  rw [this]

/-! ## One kink -/

/-- Gain from one hinge `(p - p*)⁺`: `E (p_Y - p*)⁺ - (π - p*)⁺`. -/
noncomputable def hingeGain (pr C ps : ℝ) : ℝ :=
  pr * max (p1 pr C - ps) 0 + (1 - pr) * max (p0 pr C - ps) 0 - max (pr - ps) 0

/-- Positive-branch threshold `a⁺` exactly as in Theorem 6.1. -/
noncomputable def aPlus (pr ps : ℝ) : ℝ :=
  if pr ≤ ps then (ps - pr) * pr else (pr - ps) * (1 - pr)

/-- Negative-branch threshold `a⁻` exactly as in Theorem 6.1. -/
noncomputable def aMinus (pr ps : ℝ) : ℝ :=
  if pr ≤ ps then (ps - pr) * (1 - pr) else (pr - ps) * pr

theorem hingeGain_eq (pr C ps : ℝ) (h0 : 0 < pr) (h1 : pr < 1) :
    hingeGain pr C ps
      = max (pr * (pr - ps) + C) 0 + max ((1 - pr) * (pr - ps) - C) 0
        - max (pr - ps) 0 := by
  have hne : (1 : ℝ) - pr ≠ 0 := (sub_pos.mpr h1).ne'
  have e1 : pr * max (p1 pr C - ps) 0 = max (pr * (pr - ps) + C) 0 := by
    rw [mul_max_of_nonneg _ _ h0.le, mul_zero]
    congr 1
    unfold p1; field_simp; ring
  have e0 : (1 - pr) * max (p0 pr C - ps) 0 = max ((1 - pr) * (pr - ps) - C) 0 := by
    rw [mul_max_of_nonneg _ _ (sub_pos.mpr h1).le, mul_zero]
    congr 1
    unfold p0; field_simp; ring
  unfold hingeGain
  rw [e1, e0]

/-- Theorem 6.1, one kink, `C ≥ 0` branch. -/
theorem hinge_pos (pr C ps : ℝ) (h0 : 0 < pr) (h1 : pr < 1) (hC : 0 ≤ C) :
    hingeGain pr C ps = max (C - aPlus pr ps) 0 := by
  rw [hingeGain_eq pr C ps h0 h1]
  unfold aPlus
  split_ifs with h
  · have hp : 0 ≤ (1 - pr) * (ps - pr) := mul_nonneg (by linarith) (by linarith)
    rw [max_eq_right (by linarith : (1 - pr) * (pr - ps) - C ≤ 0),
      max_eq_right (by linarith : pr - ps ≤ 0)]
    rw [show pr * (pr - ps) + C = C - (ps - pr) * pr by ring]
    ring
  · push Not at h
    have hp : 0 ≤ pr * (pr - ps) := mul_nonneg h0.le (by linarith)
    rw [max_eq_left (by linarith : (0 : ℝ) ≤ pr * (pr - ps) + C),
      max_eq_left (by linarith : (0 : ℝ) ≤ pr - ps)]
    rcases le_total ((1 - pr) * (pr - ps) - C) 0 with h2 | h2
    · rw [max_eq_right h2, max_eq_left (by linarith : (0 : ℝ) ≤ C - (pr - ps) * (1 - pr))]
      ring
    · rw [max_eq_left h2, max_eq_right (by linarith : C - (pr - ps) * (1 - pr) ≤ 0)]
      ring

/-- Theorem 6.1, one kink, `C < 0` branch. -/
theorem hinge_neg (pr C ps : ℝ) (h0 : 0 < pr) (h1 : pr < 1) (hC : C < 0) :
    hingeGain pr C ps = max (-C - aMinus pr ps) 0 := by
  rw [hingeGain_eq pr C ps h0 h1]
  unfold aMinus
  split_ifs with h
  · have hp : 0 ≤ pr * (ps - pr) := mul_nonneg h0.le (by linarith)
    rw [max_eq_right (by linarith : pr * (pr - ps) + C ≤ 0),
      max_eq_right (by linarith : pr - ps ≤ 0)]
    rw [show (1 - pr) * (pr - ps) - C = -C - (ps - pr) * (1 - pr) by ring]
    ring
  · push Not at h
    have hp : 0 ≤ (1 - pr) * (pr - ps) := mul_nonneg (by linarith) (by linarith)
    rw [max_eq_left (by linarith : (0 : ℝ) ≤ (1 - pr) * (pr - ps) - C),
      max_eq_left (by linarith : (0 : ℝ) ≤ pr - ps)]
    rcases le_total (pr * (pr - ps) + C) 0 with h2 | h2
    · rw [max_eq_right h2, max_eq_left (by linarith : (0 : ℝ) ≤ -C - (pr - ps) * pr)]
      ring
    · rw [max_eq_left h2, max_eq_right (by linarith : -C - (pr - ps) * pr ≤ 0)]
      ring

/-! ## Polyhedral value function: the full hinge law -/

/-- Polyhedral value function in hinge form:
`ψ(p) = c + s·p + Σ_k Δs_k (p - p*_k)⁺` (the representation the proof of
Theorem 6.1 starts from). -/
noncomputable def psiPoly {K : ℕ} (c s : ℝ) (ds ps : Fin K → ℝ) (p : ℝ) : ℝ :=
  c + s * p + ∑ k, ds k * max (p - ps k) 0

/-- Bayes envelope for the delayed binary sample:
`Δ = P(Y=1) ψ(p₁) + P(Y=0) ψ(p₀) - ψ(π)`. -/
noncomputable def bayesDelta (ψ : ℝ → ℝ) (pr C : ℝ) : ℝ :=
  pr * ψ (p1 pr C) + (1 - pr) * ψ (p0 pr C) - ψ pr

theorem bayesDelta_poly {K : ℕ} (c s : ℝ) (ds ps : Fin K → ℝ) (pr C : ℝ)
    (h0 : 0 < pr) (h1 : pr < 1) :
    bayesDelta (psiPoly c s ds ps) pr C = ∑ k, ds k * hingeGain pr C (ps k) := by
  have hm := posterior_mean pr C h0 h1
  unfold bayesDelta psiPoly hingeGain
  have e : ∀ k, ds k * (pr * max (p1 pr C - ps k) 0 + (1 - pr) * max (p0 pr C - ps k) 0
        - max (pr - ps k) 0)
      = pr * (ds k * max (p1 pr C - ps k) 0) + (1 - pr) * (ds k * max (p0 pr C - ps k) 0)
        - ds k * max (pr - ps k) 0 := fun k => by ring
  rw [Finset.sum_congr rfl (fun k _ => e k), Finset.sum_sub_distrib, Finset.sum_add_distrib,
    ← Finset.mul_sum, ← Finset.mul_sum]
  linear_combination s * hm

/-- **Theorem 6.1 (hinge law), positive branch**:
`Δ(C) = Σ_k Δs_k (C - a⁺_k)⁺` for `C ≥ 0`. -/
theorem hinge_law_pos {K : ℕ} (c s : ℝ) (ds ps : Fin K → ℝ) (pr C : ℝ)
    (h0 : 0 < pr) (h1 : pr < 1) (hC : 0 ≤ C) :
    bayesDelta (psiPoly c s ds ps) pr C = ∑ k, ds k * max (C - aPlus pr (ps k)) 0 := by
  rw [bayesDelta_poly c s ds ps pr C h0 h1]
  exact Finset.sum_congr rfl (fun k _ => by rw [hinge_pos pr C (ps k) h0 h1 hC])

/-- **Theorem 6.1 (hinge law), negative branch**:
`Δ(C) = Σ_k Δs_k ((-C) - a⁻_k)⁺` for `C < 0`. -/
theorem hinge_law_neg {K : ℕ} (c s : ℝ) (ds ps : Fin K → ℝ) (pr C : ℝ)
    (h0 : 0 < pr) (h1 : pr < 1) (hC : C < 0) :
    bayesDelta (psiPoly c s ds ps) pr C = ∑ k, ds k * max (-C - aMinus pr (ps k)) 0 := by
  rw [bayesDelta_poly c s ds ps pr C h0 h1]
  exact Finset.sum_congr rfl (fun k _ => by rw [hinge_neg pr C (ps k) h0 h1 hC])

/-- A two-action (finite) value function `max(α₀ + β₀ p, α₁ + β₁ p)` with
`β₁ > β₀` is polyhedral in hinge form with one kink at the indifference point
and slope jump `β₁ - β₀`. -/
theorem two_action_hinge_form (a0 b0 a1 b1 p : ℝ) (hb : b0 < b1) :
    max (a0 + b0 * p) (a1 + b1 * p)
      = a0 + b0 * p + (b1 - b0) * max (p - (a0 - a1) / (b1 - b0)) 0 := by
  have hd : 0 < b1 - b0 := by linarith
  rw [mul_max_of_nonneg _ _ hd.le, mul_zero,
    show (b1 - b0) * (p - (a0 - a1) / (b1 - b0)) = (a1 + b1 * p) - (a0 + b0 * p) by
      field_simp; ring]
  rcases le_total (a0 + b0 * p) (a1 + b1 * p) with h | h
  · rw [max_eq_right h, max_eq_left (by linarith)]; ring
  · rw [max_eq_left h, max_eq_right (by linarith)]; ring

/-! ## Worked examples -/

/-- Remark 6.4: `π = .2, p* = .3` gives `a⁺ = (0.1)(0.2) = .02`. -/
theorem example_aPlus : aPlus 0.2 0.3 = 0.02 := by
  unfold aPlus; rw [if_pos (by norm_num)]; norm_num

/-- Remark 6.4: `a⁻ = (0.1)(0.8) = .08`. -/
theorem example_aMinus : aMinus 0.2 0.3 = 0.08 := by
  unfold aMinus; rw [if_pos (by norm_num)]; norm_num

/-- Remark 6.4: covariance `+0.03` clears its threshold and has value
(one kink, `Δs = 1`: value `0.01`). -/
theorem example_pos_value : hingeGain 0.2 0.03 0.3 = 0.01 := by
  rw [hinge_pos _ _ _ (by norm_num) (by norm_num) (by norm_num), example_aPlus]
  norm_num

/-- Remark 6.4: covariance `-0.03` sits inside its threshold and is worthless. -/
theorem example_neg_worthless : hingeGain 0.2 (-0.03) 0.3 = 0 := by
  rw [hinge_neg _ _ _ (by norm_num) (by norm_num) (by norm_num), example_aMinus]
  norm_num

/-- Figure caption: for `π = .2, p* = .3` the negative-branch threshold `.08`
exceeds the whole feasible negative range `[-π², 0) = [-.04, 0)`: anticorrelated
sensing is worthless at every achievable covariance. -/
theorem example_neg_infeasible (C : ℝ)
    (hfeas : 0 ≤ q11 0.2 C ∧ 0 ≤ q10 0.2 C ∧ 0 ≤ q01 0.2 C ∧ 0 ≤ q00 0.2 C)
    (hC : C < 0) : hingeGain 0.2 C 0.3 = 0 := by
  have hr := (feasible_iff_of_le_half 0.2 C (by norm_num)).mp hfeas
  rw [hinge_neg _ _ _ (by norm_num) (by norm_num) hC, example_aMinus]
  apply max_eq_right
  norm_num at hr ⊢
  linarith [hr.1]

/-- Figure 3 parameters `π = .35, p* = .45`: `a⁺ = .035`. -/
theorem figure_aPlus : aPlus 0.35 0.45 = 0.035 := by
  unfold aPlus; rw [if_pos (by norm_num)]; norm_num

/-- Figure 3 parameters: `a⁻ = .065`. -/
theorem figure_aMinus : aMinus 0.35 0.45 = 0.065 := by
  unfold aMinus; rw [if_pos (by norm_num)]; norm_num

/-- Figure 3 axis: feasible range at `π = .35` is `[-.1225, .2275] = [-π², π(1-π)]`. -/
theorem figure_feasible (C : ℝ) :
    (0 ≤ q11 0.35 C ∧ 0 ≤ q10 0.35 C ∧ 0 ≤ q01 0.35 C ∧ 0 ≤ q00 0.35 C) ↔
    (-0.1225 ≤ C ∧ C ≤ 0.2275) := by
  rw [feasible_iff_of_le_half _ _ (by norm_num)]
  norm_num

/-- Dead-zone remark (line 654): for `p* > π` the negative-branch threshold is
larger by the factor `(1-π)/π`. -/
theorem threshold_ratio (pr ps : ℝ) (h0 : 0 < pr) (h : pr < ps) :
    aMinus pr ps = (1 - pr) / pr * aPlus pr ps := by
  unfold aMinus aPlus
  rw [if_pos h.le, if_pos h.le]
  field_simp

/-! ## Corollary 6.5 (the companion law) -/

/-- The `0/1` prediction value `max(p, 1-p)` is the hinge form with
`c = 1, s = -1`, one kink `p* = 1/2`, slope jump `Δs = 2`. -/
theorem zero_one_hinge_form (p : ℝ) :
    max p (1 - p) = psiPoly (K := 1) 1 (-1) (fun _ => 2) (fun _ => 1 / 2) p := by
  unfold psiPoly
  simp only [Fin.sum_univ_one]
  rcases le_total p (1 - p) with h | h
  · rw [max_eq_right h, max_eq_right (by linarith : p - 1 / 2 ≤ 0)]; ring
  · rw [max_eq_left h, max_eq_left (by linarith : (0 : ℝ) ≤ p - 1 / 2)]; ring

/-- Symmetric chain: joint mass `(1+r)/4` on agreeing pairs gives `C = r/4`. -/
theorem symmetric_cov (r : ℝ) : (1 + r) / 4 - (1 / 2) * (1 / 2) = r / 4 := by ring

/-- **Corollary 6.5**: at `π = 1/2, p* = 1/2, Δs = 2` both thresholds vanish and
`Δ = 2 · |C| = 2 · |r|/4 = |r|/2` on both branches. -/
theorem companion_law (r : ℝ) :
    bayesDelta (fun p => max p (1 - p)) (1 / 2) (r / 4) = |r| / 2 := by
  have hf : (fun p : ℝ => max p (1 - p))
      = psiPoly (K := 1) 1 (-1) (fun _ => 2) (fun _ => 1 / 2) := by
    funext p; exact zero_one_hinge_form p
  rw [hf, bayesDelta_poly _ _ _ _ _ _ (by norm_num) (by norm_num), Fin.sum_univ_one]
  rcases le_or_gt 0 r with h | h
  · rw [hinge_pos _ _ _ (by norm_num) (by norm_num) (by linarith)]
    unfold aPlus; rw [if_pos le_rfl, abs_of_nonneg h]
    rw [max_eq_left (by linarith)]; ring
  · rw [hinge_neg _ _ _ (by norm_num) (by norm_num) (by linarith)]
    unfold aMinus; rw [if_pos le_rfl, abs_of_neg h]
    rw [max_eq_left (by linarith)]; ring

end PredictiveValue
