# Signature Distance v1 (Pinned)

This document defines how to compute `family_signature_v1` and the distance metric `d`.

## Signature Derivation

Given the family object `f`:

1. Construct `f_base` by removing `family_id` and `signature` fields.
2. Compute `h = sha256(canon_bytes(f_base))`.
3. Decode the 32-byte hash.
4. For each field i in order, set `field_i = hash_bytes[i] % 16`.

Field order:

1. `obs_class`
2. `nuisance_class`
3. `action_remap_class`
4. `delay_class`
5. `noise_class`
6. `render_class`

Each field is an integer in `[0, 15]`.

## Distance

Weighted Hamming:

`d(sig_a, sig_b) = sum_i w_i * 1[field_i differs]`

Pinned weights: `w_i = 1` for all fields.
