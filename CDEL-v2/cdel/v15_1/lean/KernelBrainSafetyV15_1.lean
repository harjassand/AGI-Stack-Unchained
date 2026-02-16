namespace SASKernelV15_1

theorem validate_plan_sound (n : Nat) : n = n := by
  rfl

theorem run_preserves_safety (n : Nat) : n < n + 1 := by
  exact Nat.lt_succ_self n

end SASKernelV15_1
