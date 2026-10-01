# Lean check of "The Value of Delayed Information"

Machine-checked finite and algebraic results of the paper, in Lean 4 with Mathlib `v4.32.2`.

```
lake exe cache get
lake build
lake env lean Axioms.lean
```

52 theorems, no `sorry`; each depends only on `propext`, `Classical.choice` and `Quot.sound`.

| file | paper results |
|---|---|
| `PredictiveValue/Lipschitz.lean` | Lemma 2.1 (finite states and actions) |
| `PredictiveValue/Hinge.lean` | binary posteriors and exact feasible range; Theorem 6.1 hinge law on both branches; Remark 6.4 and Figure 3 values; Corollary 6.5 |
| `PredictiveValue/Smooth.lean` | Proposition 6.2 (squared error); Theorem 6.3 contact weights (exact-power profile) |
| `PredictiveValue/Information.lean` | Proposition 4.1 two-bit construction; fair-pair I(r) closed form and value; Corollary 3.2 arithmetic |

Not formalized: the Pinsker-based envelopes (Theorem 3.1, Lemma 3.3, Theorem 3.4, Proposition 5.1; Mathlib has no Pinsker inequality), the preview process and beta-mixing, asymptotic expansions (checked symbolically in `../symbolic/`), and the layer-cake decomposition.
