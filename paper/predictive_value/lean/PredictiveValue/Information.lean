import Mathlib

/-!
# Mutual information for finite joints; Proposition 4.1 (two-bit construction);
# Proposition 3.5 (binary-pair information identity and exact value); Corollary 3.2

Paper: `sigmetrics.tex` lines 285-308 (`prop:tight`), 313-331 (`prop:noneq`),
205-214 (`cor:bits`), Appendix "Binary chain" (line 1079).

Mutual information of a finite joint `q : α → β → ℝ` is defined as
`I = H(X) + H(Y) - H(X,Y)` with `H(p) = Σ negMulLog (p i)` (nats).
-/

open Finset Real

namespace PredictiveValue

/-- Shannon entropy in nats of a finite vector. -/
noncomputable def ent {ι : Type*} [Fintype ι] (p : ι → ℝ) : ℝ := ∑ i, negMulLog (p i)

/-- Mutual information `I(X;Y) = H(X) + H(Y) - H(X,Y)` of a finite joint law. -/
noncomputable def mutualInfo {α β : Type*} [Fintype α] [Fintype β] (q : α → β → ℝ) : ℝ :=
  ent (fun a => ∑ b, q a b) + ent (fun b => ∑ a, q a b) - ent (fun ab : α × β => q ab.1 ab.2)

/-- Bayes envelope of an observation for a two-action problem with reward `R`:
`Σ_y max_w Σ_x R(w,x) q(x,y) - max_w Σ_x R(w,x) P(x)`, i.e. `E ψ(μ_Y) - ψ(μ̄)`
written with unnormalized posteriors. -/
noncomputable def gain2 {α β : Type*} [Fintype α] [Fintype β]
    (R : Fin 2 → α → ℝ) (q : α → β → ℝ) : ℝ :=
  (∑ b, max (∑ a, R 0 a * q a b) (∑ a, R 1 a * q a b))
    - max (∑ a, R 0 a * ∑ b, q a b) (∑ a, R 1 a * ∑ b, q a b)

/-! ## Proposition 4.1 -/

/-- State `X = (B₁, B₂)` two independent fair bits, observation `Y₁ = B₁`. -/
noncomputable def jointY1 (x : Fin 2 × Fin 2) (y : Fin 2) : ℝ := if y = x.1 then 1 / 4 else 0
/-- Observation `Y₂ = B₂`. -/
noncomputable def jointY2 (x : Fin 2 × Fin 2) (y : Fin 2) : ℝ := if y = x.2 then 1 / 4 else 0
/-- Objective depending only on `B₁`: `R(w,x) = Ω · 1[w = B₁]`. -/
noncomputable def rewardB1 (Ω : ℝ) (w : Fin 2) (x : Fin 2 × Fin 2) : ℝ :=
  if w = x.1 then Ω else 0

theorem negMulLog_quarter : negMulLog (1 / 4 : ℝ) = log 2 / 2 := by
  rw [negMulLog, one_div, log_inv, show (4 : ℝ) = 2 ^ 2 by norm_num, log_pow]
  push_cast; ring

theorem negMulLog_div4 (a : ℝ) (ha : a ≠ 0) :
    negMulLog (a / 4) = -(a / 4) * (log a - 2 * log 2) := by
  rw [negMulLog, log_div ha (by norm_num), show (4 : ℝ) = 2 ^ 2 by norm_num, log_pow]
  push_cast; ring

theorem negMulLog_half : negMulLog (1 / 2 : ℝ) = log 2 / 2 := by
  rw [negMulLog, one_div, log_inv]; ring

theorem mi_Y1 : mutualInfo jointY1 = log 2 := by
  simp only [mutualInfo, ent, jointY1, Fintype.sum_prod_type, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte, add_zero, zero_add, negMulLog_zero]
  rw [show (1 / 4 : ℝ) + 1 / 4 = 1 / 2 by norm_num, negMulLog_quarter, negMulLog_half]
  ring

theorem mi_Y2 : mutualInfo jointY2 = log 2 := by
  simp only [mutualInfo, ent, jointY2, Fintype.sum_prod_type, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte, add_zero, zero_add, negMulLog_zero]
  rw [show (1 / 4 : ℝ) + 1 / 4 = 1 / 2 by norm_num, negMulLog_quarter, negMulLog_half]
  ring

/-- Prop 4.1: the objective has oscillation `Ω` (for `Ω ≥ 0`). -/
theorem rewardB1_range (Ω : ℝ) (w : Fin 2) (x : Fin 2 × Fin 2) (hΩ : 0 ≤ Ω) :
    0 ≤ rewardB1 Ω w x ∧ rewardB1 Ω w x ≤ Ω := by
  unfold rewardB1; split_ifs <;> constructor <;> linarith

/-- Prop 4.1: observing `B₁` is worth `Ω/2`. -/
theorem gain_Y1 (Ω : ℝ) (hΩ : 0 ≤ Ω) : gain2 (rewardB1 Ω) jointY1 = Ω / 2 := by
  simp only [gain2, rewardB1, jointY1, Fintype.sum_prod_type, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte]
  norm_num
  rw [max_eq_left (by linarith), max_eq_right (by linarith)]
  ring

/-- Prop 4.1: observing `B₂` is worth `0`. -/
theorem gain_Y2 (Ω : ℝ) : gain2 (rewardB1 Ω) jointY2 = 0 := by
  simp only [gain2, rewardB1, jointY2, Fintype.sum_prod_type, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte]
  norm_num
  try ring

/-- **Proposition 4.1**: equal positive information `log 2`, values `Ω/2` vs `0`;
hence no `f` with `Δ = f(I)` exists (for `Ω > 0`). -/
theorem no_universal_f (Ω : ℝ) (hΩ : 0 < Ω) :
    mutualInfo jointY1 = mutualInfo jointY2 ∧ 0 < mutualInfo jointY1 ∧
    gain2 (rewardB1 Ω) jointY1 = Ω / 2 ∧ gain2 (rewardB1 Ω) jointY2 = 0 ∧
    ¬ ∃ f : ℝ → ℝ, ∀ q ∈ [jointY1, jointY2],
        gain2 (rewardB1 Ω) q = f (mutualInfo q) := by
  refine ⟨by rw [mi_Y1, mi_Y2], by rw [mi_Y1]; exact log_pos (by norm_num),
    gain_Y1 Ω hΩ.le, gain_Y2 Ω, ?_⟩
  rintro ⟨f, hf⟩
  have h1 := hf jointY1 (by simp)
  have h2 := hf jointY2 (by simp)
  rw [gain_Y1 Ω hΩ.le, mi_Y1] at h1
  rw [gain_Y2 Ω, mi_Y2] at h2
  linarith

/-! ## Proposition 3.5 and the Appendix binary chain -/

/-- Stationary fair binary pair with correlation `r`:
mass `(1+r)/4` on agreeing pairs, `(1-r)/4` on disagreeing pairs. -/
noncomputable def fairPair (r : ℝ) (x y : Fin 2) : ℝ := if x = y then (1 + r) / 4 else (1 - r) / 4

/-- **Proposition 3.5 (identity part)**:
`I(X_t; X_{t-D}) = ½[(1+r) ln(1+r) + (1-r) ln(1-r)]` for `|r| < 1`. -/
theorem mi_fairPair (r : ℝ) (h1 : -1 < r) (h2 : r < 1) :
    mutualInfo (fairPair r)
      = (1 / 2) * ((1 + r) * log (1 + r) + (1 - r) * log (1 - r)) := by
  have ha : (1 + r) ≠ 0 := by linarith
  have hb : (1 - r) ≠ 0 := by linarith
  simp only [mutualInfo, ent, fairPair, Fintype.sum_prod_type, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte]
  have e1 : (1 + r) / 4 + (1 - r) / 4 = 1 / 2 := by ring
  have e2 : (1 - r) / 4 + (1 + r) / 4 = 1 / 2 := by ring
  rw [e1, e2, negMulLog_half, negMulLog_div4 _ ha, negMulLog_div4 _ hb]
  ring

/-- Appendix (binary chain) / Prop 3.5: exact single-sample value of the `0/1`
prediction objective `R(w,x) = 1[w = x]` is `|r|/2`. -/
theorem fairPair_value (r : ℝ) :
    gain2 (fun w x => if w = x then (1 : ℝ) else 0) (fairPair r) = |r| / 2 := by
  simp only [gain2, fairPair, Fin.sum_univ_two]
  simp only [Fin.isValue, Fin.reduceEq, ↓reduceIte]
  simp only [max_def]
  rcases abs_cases r with ⟨h1, h2⟩ | ⟨h1, h2⟩ <;> rw [h1] <;> split_ifs <;> linarith

/-- Appendix / Prop 5.2(i) ingredient: the posterior after either delayed value is at
total variation `|r|/2` from the uniform prior. -/
theorem fairPair_posterior_tv (r : ℝ) :
    (1 / 2) * (|(1 + r) / 2 - 1 / 2| + |(1 - r) / 2 - 1 / 2|) = |r| / 2 := by
  rw [show (1 + r) / 2 - 1 / 2 = r / 2 by ring, show (1 - r) / 2 - 1 / 2 = -(r / 2) by ring,
    abs_neg, abs_div, abs_two]
  ring

/-! ## Corollary 3.2 arithmetic -/

theorem two_lt_two_div_log_two : 2 < 2 / log 2 := by
  have h := log_two_lt_d9
  have hp : 0 < log 2 := log_pos (by norm_num)
  rw [lt_div_iff₀ hp]
  linarith

theorem two_div_log_two_lt_three : 2 / log 2 < 3 := by
  have h := log_two_gt_d9
  have hp : 0 < log 2 := log_pos (by norm_num)
  rw [div_lt_iff₀ hp]
  linarith

/-- Corollary 3.2: `Ω √(b ln2 / 2) ≥ Ω` iff `b ≥ 2 / ln 2` (`Ω > 0`). -/
theorem bitbudget_vacuous_iff (Ω b : ℝ) (hΩ : 0 < Ω) :
    Ω ≤ Ω * sqrt (b * log 2 / 2) ↔ 2 / log 2 ≤ b := by
  have hp : 0 < log 2 := log_pos (by norm_num)
  rw [le_mul_iff_one_le_right hΩ, one_le_sqrt, div_le_iff₀ hp, le_div_iff₀ (by norm_num)]
  constructor <;> intro h <;> linarith

/-- Corollary 3.2: for an integer bit budget the square-root bound beats the trivial
bound `Ω` exactly when `b ≤ 2` (so the clip is active from `b = 3` on). -/
theorem bitbudget_bites_nat (Ω : ℝ) (hΩ : 0 < Ω) (b : ℕ) :
    Ω * sqrt ((b : ℝ) * log 2 / 2) < Ω ↔ b ≤ 2 := by
  rw [← not_le, bitbudget_vacuous_iff Ω b hΩ, not_le]
  have h2 := two_lt_two_div_log_two
  have h3 := two_div_log_two_lt_three
  constructor
  · intro h
    by_contra hb
    push Not at hb
    have : (3 : ℝ) ≤ b := by exact_mod_cast hb
    linarith
  · intro hb
    have : (b : ℝ) ≤ 2 := by exact_mod_cast hb
    linarith

end PredictiveValue
