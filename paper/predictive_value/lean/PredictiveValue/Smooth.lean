import PredictiveValue.Hinge

/-!
# Proposition 6.2 (squared error, exactly quadratic) and Theorem 6.3 (contact order)

Paper: `sigmetrics.tex` lines 557-584 (`prop:quadratic`), 586-611 (`thm:contact`).
-/

namespace PredictiveValue

/-- Expected squared-error reward of action `w` under belief `p = P(X=1)`:
`-(p (w-1)² + (1-p) w²)`. -/
def sqReward (p w : ℝ) : ℝ := -(p * (w - 1) ^ 2 + (1 - p) * w ^ 2)

/-- Prop 6.2: `ψ(p) = sup_{w∈[0,1]} E[-(w-X)²] = -p(1-p)`, attained at `w = p`. -/
theorem sq_value_isGreatest (p : ℝ) (h0 : 0 ≤ p) (h1 : p ≤ 1) :
    IsGreatest {v | ∃ w ∈ Set.Icc (0 : ℝ) 1, v = sqReward p w} (-(p * (1 - p))) := by
  refine ⟨⟨p, ⟨h0, h1⟩, by unfold sqReward; ring⟩, ?_⟩
  rintro v ⟨w, _, rfl⟩
  unfold sqReward
  nlinarith [sq_nonneg (w - p)]

/-- Prop 6.2 value function `ψ(p) = p² - p`. -/
def psiSq (p : ℝ) : ℝ := p ^ 2 - p

/-- **Proposition 6.2**: `Δ = C² / (π(1-π))` exactly. -/
theorem quadratic_delta (pr C : ℝ) (h0 : 0 < pr) (h1 : pr < 1) :
    bayesDelta psiSq pr C = C ^ 2 / (pr * (1 - pr)) := by
  have : (1 : ℝ) - pr ≠ 0 := (sub_pos.mpr h1).ne'
  have : pr ≠ 0 := h0.ne'
  unfold bayesDelta psiSq p1 p0
  field_simp
  ring

/-- Prop 6.2: `Var(p_Y) = C² / (π(1-π))` (the posterior has mean `π`). -/
theorem posterior_variance (pr C : ℝ) (h0 : 0 < pr) (h1 : pr < 1) :
    pr * (p1 pr C - pr) ^ 2 + (1 - pr) * (p0 pr C - pr) ^ 2 = C ^ 2 / (pr * (1 - pr)) := by
  have : (1 : ℝ) - pr ≠ 0 := (sub_pos.mpr h1).ne'
  have : pr ≠ 0 := h0.ne'
  unfold p1 p0
  field_simp
  ring

/-- Contact profile `ψ(π+h) = ψ(π) + a h + c₊ h₊^q + c₋ (-h)₊^q`
(Theorem 6.3 with the `o(|h|^q)` remainder set to zero). -/
noncomputable def contactPsi (pr v a cp cm q : ℝ) (p : ℝ) : ℝ :=
  v + a * (p - pr) + cp * (max (p - pr) 0) ^ q + cm * (max (pr - p) 0) ^ q

/-- **Theorem 6.3, exact power profile, `C > 0`**:
`Δ(C) = C^q [c₊ π^{1-q} + c₋ (1-π)^{1-q}]`. -/
theorem contact_pos (pr v a cp cm q C : ℝ) (h0 : 0 < pr) (h1 : pr < 1) (hq : q ≠ 0)
    (hC : 0 < C) :
    bayesDelta (contactPsi pr v a cp cm q) pr C
      = C ^ q * (cp * pr ^ (1 - q) + cm * (1 - pr) ^ (1 - q)) := by
  have h1' : 0 < 1 - pr := sub_pos.mpr h1
  have hm := posterior_mean pr C h0 h1
  have ea : p1 pr C - pr = C / pr := by unfold p1; ring
  have eb : pr - p0 pr C = C / (1 - pr) := by unfold p0; ring
  have hA : 0 < C / pr := div_pos hC h0
  have hB : 0 < C / (1 - pr) := div_pos hC h1'
  unfold bayesDelta contactPsi
  rw [ea, show pr - p1 pr C = -(C / pr) by rw [← ea]; ring,
    show p0 pr C - pr = -(C / (1 - pr)) by rw [← eb]; ring, eb]
  rw [max_eq_left hA.le, max_eq_right (by linarith : -(C / pr) ≤ 0),
    max_eq_right (by linarith : -(C / (1 - pr)) ≤ 0), max_eq_left hB.le,
    sub_self, max_self, Real.zero_rpow hq]
  rw [Real.div_rpow hC.le h0.le, Real.div_rpow hC.le h1'.le,
    Real.rpow_sub h0, Real.rpow_sub h1', Real.rpow_one, Real.rpow_one]
  have hp : 0 < pr ^ q := Real.rpow_pos_of_pos h0 q
  have hp' : 0 < (1 - pr) ^ q := Real.rpow_pos_of_pos h1' q
  field_simp
  ring

/-- **Theorem 6.3, exact power profile, `C < 0`**: weights `π ↔ 1-π` interchanged. -/
theorem contact_neg (pr v a cp cm q C : ℝ) (h0 : 0 < pr) (h1 : pr < 1) (hq : q ≠ 0)
    (hC : C < 0) :
    bayesDelta (contactPsi pr v a cp cm q) pr C
      = |C| ^ q * (cp * (1 - pr) ^ (1 - q) + cm * pr ^ (1 - q)) := by
  have h1' : 0 < 1 - pr := sub_pos.mpr h1
  have hm := posterior_mean pr C h0 h1
  set D := -C with hD
  have hDp : 0 < D := by linarith
  have habs : |C| = D := by rw [abs_of_neg hC]
  have ea : pr - p1 pr C = D / pr := by unfold p1; rw [hD]; ring
  have eb : p0 pr C - pr = D / (1 - pr) := by unfold p0; rw [hD]; ring
  have hA : 0 < D / pr := div_pos hDp h0
  have hB : 0 < D / (1 - pr) := div_pos hDp h1'
  unfold bayesDelta contactPsi
  rw [ea, show p1 pr C - pr = -(D / pr) by rw [← ea]; ring,
    show pr - p0 pr C = -(D / (1 - pr)) by rw [← eb]; ring, eb, habs]
  rw [max_eq_left hA.le, max_eq_right (by linarith : -(D / pr) ≤ 0),
    max_eq_right (by linarith : -(D / (1 - pr)) ≤ 0), max_eq_left hB.le,
    sub_self, max_self, Real.zero_rpow hq]
  rw [Real.div_rpow hDp.le h0.le, Real.div_rpow hDp.le h1'.le,
    Real.rpow_sub h0, Real.rpow_sub h1', Real.rpow_one, Real.rpow_one]
  have hp : 0 < pr ^ q := Real.rpow_pos_of_pos h0 q
  have hp' : 0 < (1 - pr) ^ q := Real.rpow_pos_of_pos h1' q
  field_simp
  ring

/-- Theorem 6.3 at `q = 1` reduces to the hinge at a kink sitting on the prior:
`Δ = (c₊ + c₋) |C|`, i.e. slope jump `Δs = c₊ + c₋`, zero threshold. -/
theorem contact_q1_is_kink_hinge (pr v a cp cm C : ℝ) (h0 : 0 < pr) (h1 : pr < 1)
    (hC : 0 < C) :
    bayesDelta (contactPsi pr v a cp cm 1) pr C = (cp + cm) * C := by
  rw [contact_pos pr v a cp cm 1 C h0 h1 one_ne_zero hC]
  simp only [Real.rpow_one, sub_self, Real.rpow_zero, mul_one]
  ring

end PredictiveValue
