# DP Accountant Validation Plan (Normative)

## Implemented Mechanism
The DP accountant uses basic composition over per-call (epsilon, delta) spends. Each evaluation consumes the bid-specified privacy budget when a private dataset is queried.

## Invariants
- Monotonic spend: epsilon_spent and delta_spent MUST never decrease.
- No overspend: total spend MUST NOT exceed epoch totals.
- Refusal before evaluation: if the remaining budget is insufficient, evaluation MUST fail with spend=0.

## Validation Procedure
1. Initialize a fresh epoch ledger with known totals.
2. Submit repeated evaluations with fixed privacy bids until the ledger is exhausted.
3. Confirm:
   - spends are monotonic and exact,
   - refusal occurs immediately once remaining budget is insufficient,
   - refusal does not run evaluation or emit receipts.
4. Record ledger snapshots before and after each call.

## Expected Outputs
- A deterministic report listing spend progression and refusal point.
- Explicit PASS/FAIL for each invariant.
