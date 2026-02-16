# AlphaLedger Correctness Proof Sketch (Normative)

## Statement
For DeploymentGrade admissions, the probability of any false admission within an epoch is bounded by alpha_total under the alpha-spending schedule.

## Assumptions
- Each admission test at attempt i is conducted at significance level alpha_i.
- The spending schedule satisfies sum_i alpha_i <= alpha_total.
- Tests are valid for their declared alpha_i.

## Proof Sketch
1. By construction, the schedule enforces sum_i alpha_i <= alpha_total.
2. By the union bound, the probability of at least one false admission is at most the sum of per-attempt false admission probabilities.
3. Therefore, P(any false admission) <= sum_i alpha_i <= alpha_total.

## Ledger Invariants
- alpha_spent is monotonic increasing.
- alpha_remaining = alpha_total - alpha_spent is nonnegative.
- If alpha_remaining is insufficient for the next attempt, admission is refused before evaluation.
- Every PASS receipt records the alpha_spent for that attempt.
