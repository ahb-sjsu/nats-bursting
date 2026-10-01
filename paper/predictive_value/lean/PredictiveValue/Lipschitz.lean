import Mathlib

/-!
# Lemma 2.1 (Lipschitz value in total variation)

Paper: `sigmetrics.tex` line 170, `\label{lem:lip}`.

Finite state space `α`, finite nonempty action set `W`, reward `R w x` bounded in
`[m, M]` (so its oscillation is at most `Ω = M - m`).  Beliefs are real vectors
summing to one (nonnegativity is not even needed for the inequality).
-/

open Finset

namespace PredictiveValue

/-- Total variation distance `(1/2) Σ |μ - μ'|` on a finite type. -/
noncomputable def tv {α : Type*} [Fintype α] (μ μ' : α → ℝ) : ℝ :=
  (1 / 2) * ∑ x, |μ x - μ' x|

/-- Value of a belief: `ψ(μ) = max_w Σ_x R(w,x) μ(x)` over a finite action set. -/
noncomputable def psi {W α : Type*} [Fintype W] [Nonempty W] [Fintype α]
    (R : W → α → ℝ) (μ : α → ℝ) : ℝ :=
  univ.sup' univ_nonempty (fun w => ∑ x, R w x * μ x)

/-- Lemma 2.1, single action: `|Σ R (μ - μ')| ≤ Ω · TV(μ, μ')`. -/
theorem lip_linear {α : Type*} [Fintype α] (R : α → ℝ) (m M : ℝ)
    (hR : ∀ x, m ≤ R x ∧ R x ≤ M) (μ μ' : α → ℝ)
    (hμ : ∑ x, μ x = 1) (hμ' : ∑ x, μ' x = 1) :
    |∑ x, R x * μ x - ∑ x, R x * μ' x| ≤ (M - m) * tv μ μ' := by
  set c := (M + m) / 2 with hc
  have h0 : ∑ x, (μ x - μ' x) = 0 := by
    rw [Finset.sum_sub_distrib, hμ, hμ']; ring
  have key : ∑ x, R x * μ x - ∑ x, R x * μ' x = ∑ x, (R x - c) * (μ x - μ' x) := by
    have e : ∑ x, (R x - c) * (μ x - μ' x)
        = ∑ x, R x * (μ x - μ' x) - c * ∑ x, (μ x - μ' x) := by
      rw [Finset.mul_sum, ← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl (fun x _ => by ring)
    rw [e, h0, mul_zero, sub_zero, ← Finset.sum_sub_distrib]
    exact Finset.sum_congr rfl (fun x _ => by ring)
  rw [key]
  calc |∑ x, (R x - c) * (μ x - μ' x)|
      ≤ ∑ x, |(R x - c) * (μ x - μ' x)| := Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ x, (M - m) / 2 * |μ x - μ' x| := by
        apply Finset.sum_le_sum
        intro x _
        rw [abs_mul]
        apply mul_le_mul_of_nonneg_right _ (abs_nonneg _)
        rw [abs_le]
        obtain ⟨h1, h2⟩ := hR x
        constructor <;> linarith
    _ = (M - m) * tv μ μ' := by
        rw [← Finset.mul_sum]; unfold tv; ring

/-- `|max f - max g| ≤ B` whenever `|f w - g w| ≤ B` for every `w`. -/
theorem sup'_sub_le {W : Type*} [Fintype W] [Nonempty W] (f g : W → ℝ) (B : ℝ)
    (h : ∀ w, |f w - g w| ≤ B) :
    |univ.sup' univ_nonempty f - univ.sup' univ_nonempty g| ≤ B := by
  have h1 : univ.sup' univ_nonempty f ≤ univ.sup' univ_nonempty g + B := by
    apply Finset.sup'_le
    intro w _
    have hg : g w ≤ univ.sup' univ_nonempty g := Finset.le_sup' g (Finset.mem_univ w)
    have := (abs_le.mp (h w)).2
    linarith
  have h2 : univ.sup' univ_nonempty g ≤ univ.sup' univ_nonempty f + B := by
    apply Finset.sup'_le
    intro w _
    have hf : f w ≤ univ.sup' univ_nonempty f := Finset.le_sup' f (Finset.mem_univ w)
    have := (abs_le.mp (h w)).1
    linarith
  rw [abs_le]
  constructor <;> linarith

/-- Lemma 2.1: `|ψ(μ) - ψ(μ')| ≤ Ω · TV(μ, μ')` (finite action set). -/
theorem lip_value {W α : Type*} [Fintype W] [Nonempty W] [Fintype α]
    (R : W → α → ℝ) (m M : ℝ) (hR : ∀ w x, m ≤ R w x ∧ R w x ≤ M)
    (μ μ' : α → ℝ) (hμ : ∑ x, μ x = 1) (hμ' : ∑ x, μ' x = 1) :
    |psi R μ - psi R μ'| ≤ (M - m) * tv μ μ' := by
  unfold psi
  apply sup'_sub_le
  intro w
  exact lip_linear (R w) m M (hR w) μ μ' hμ hμ'

/-- Lemma 2.1, second clause: `Δ_Y ≤ Ω · E ‖μ_Y - μ̄‖_TV` for a finite observation
alphabet `β` with law `P` and posteriors `post y`. -/
theorem envelope_le_tv {W α β : Type*} [Fintype W] [Nonempty W] [Fintype α] [Fintype β]
    (R : W → α → ℝ) (m M : ℝ) (hR : ∀ w x, m ≤ R w x ∧ R w x ≤ M)
    (P : β → ℝ) (hP0 : ∀ y, 0 ≤ P y) (hP : ∑ y, P y = 1)
    (post : β → α → ℝ) (hpost : ∀ y, ∑ x, post y x = 1)
    (prior : α → ℝ) (hprior : ∑ x, prior x = 1) :
    (∑ y, P y * psi R (post y)) - psi R prior
      ≤ (M - m) * ∑ y, P y * tv (post y) prior := by
  have e : (∑ y, P y * psi R (post y)) - psi R prior
      = ∑ y, P y * (psi R (post y) - psi R prior) := by
    have : ∑ y, P y * (psi R (post y) - psi R prior)
        = ∑ y, P y * psi R (post y) - (∑ y, P y) * psi R prior := by
      rw [Finset.sum_mul, ← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl (fun y _ => by ring)
    rw [this, hP, one_mul]
  rw [e, Finset.mul_sum]
  apply Finset.sum_le_sum
  intro y _
  have h := lip_value R m M hR (post y) prior (hpost y) hprior
  have h' : psi R (post y) - psi R prior ≤ (M - m) * tv (post y) prior :=
    le_trans (le_abs_self _) h
  calc P y * (psi R (post y) - psi R prior)
      ≤ P y * ((M - m) * tv (post y) prior) := mul_le_mul_of_nonneg_left h' (hP0 y)
    _ = (M - m) * (P y * tv (post y) prior) := by ring

end PredictiveValue
