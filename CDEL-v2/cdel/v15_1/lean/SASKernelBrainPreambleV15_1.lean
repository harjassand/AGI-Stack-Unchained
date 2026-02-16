namespace SASKernelV15_1

structure BrainContext where
  seed : Nat
  remainingBudget : Nat
  minRemainingBudget : Nat
  hardStop : Bool

structure BrainDecision where
  verdict : String
  rulePath : List String

def decide (ctx : BrainContext) : BrainDecision :=
  if ctx.hardStop then
    { verdict := "STOP", rulePath := ["R2_BUDGET_HARD_STOP"] }
  else if ctx.remainingBudget < ctx.minRemainingBudget then
    { verdict := "STOP", rulePath := ["R3_BUDGET_MIN_REMAINING"] }
  else
    { verdict := "RUN", rulePath := ["R6_TIEBREAK"] }

theorem decide_deterministic (ctx : BrainContext) : decide ctx = decide ctx := rfl

theorem rule_path_nonempty (ctx : BrainContext) : (decide ctx).rulePath.length > 0 := by
  by_cases hHard : ctx.hardStop
  · simp [decide, hHard]
  · by_cases hBudget : ctx.remainingBudget < ctx.minRemainingBudget
    · simp [decide, hHard, hBudget]
    · simp [decide, hHard, hBudget]

end SASKernelV15_1
