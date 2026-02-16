# C-META Equivalence + WorkVec v1 (Pinned)

This document pins translation equivalence and WorkVec dominance.

## Equivalence

- **E1 Byte-identity**: canonical output bytes must match exactly.

## WorkVec Fields

1. `verifier_gas_total` (lower is better)
2. `env_steps_total` (lower is better)
3. `oracle_calls_total` (lower is better)
4. `bytes_hashed_total` (lower is better)
5. `candidates_fully_evaluated` (lower is better)
6. `short_circuits_total` (higher is better)

## Dominance

Lexicographic order using the direction above. Strictness holds if the first differing field is improved by at least `EPS_WORK = 1`.
