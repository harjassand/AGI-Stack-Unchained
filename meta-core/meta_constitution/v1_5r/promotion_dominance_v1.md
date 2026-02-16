# Promotion Dominance v1 (Pinned)

This document pins the unified promotion rule for v1.5r.

## Hard Gates

All applicable contracts must pass:

- C-INV, C-MDL, C-DO, C-ANTI, C-LIFE
- SR-CEGAR novelty + learnability
- C-TIME admission / C-CRYSTAL eviction correctness
- C-META translation validation

## Anchor Non-Regression

`WorstAnchor(new, t) >= WorstAnchor(base, t)`.

## Strict Improvement (one must improve)

- `WorstHeldout` improves (0 -> 1), or
- total MDL improves by at least `DELTA_MIN_BITS = 64`, or
- WorkVec dominance strictly improves (per WorkVec rules).

## Tie-break

1. Fewer new symbols introduced
2. Smaller active macro set
3. Smaller frontier churn (min symmetric difference)
4. Lexicographically smallest hash
