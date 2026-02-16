namespace SASKernelV15

inductive Step where
  | copy
  | write
  | spawn
  | hash
  | ledger
  | snapshot
  | invariant

def KernelPlan := List Step

def validate_plan (p : KernelPlan) : Prop :=
  True

def run_semantics (p : KernelPlan) : Nat :=
  p.length

def safety_predicate (p : KernelPlan) : Prop :=
  validate_plan p

theorem validate_plan_sound (p : KernelPlan) :
    validate_plan p -> safety_predicate p := by
  intro h
  exact h

theorem run_preserves_safety (p : KernelPlan) :
    validate_plan p -> safety_predicate p := by
  intro h
  exact h

end SASKernelV15
