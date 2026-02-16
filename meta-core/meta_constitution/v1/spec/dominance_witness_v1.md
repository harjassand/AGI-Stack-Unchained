# Dominance Witness v1

This document defines the dominance witness requirements for structural OR.

## Rule form

Let the parent accept be:

```
Accept_A = SAFE AND CondA
```

The candidate accept must be:

```
Accept_B = SAFE AND (CondA OR CondExtra)
```

## Witness requirements

The candidate bundle MUST include `proofs/dominance_witness.json` with:

- `x_star` (object)
- `state_a` (value)
- `condextra_inputs` (object)

`condextra_inputs` MUST include:

- `blob_hashes`: array of lowercase hex64 strings

Each `blob_hash` must exist in the bundle manifest blob list.

## Kernel checks

The kernel enforces:

1. `CondA(x_star, state_a)` is **false**.
2. `CondExtra(x_star, condextra_inputs)` is **true**.

`CondA` is extracted from the parent accept.
`CondExtra` is the non-parent branch of the candidate `Or`.
