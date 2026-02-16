# Receipt Verification (Level-1)

Receipts are PASS-only objects. This document defines how receipts are verified and what they bind.

## Normative Default (MUST implement)

- Receipt format: `schema/receipt.schema.json`
- Canonicalization: GCJ-1
- Hash: SHA-256

## What a Receipt Binds

A valid receipt MUST bind:

- `capsule_hash`
- `epoch_id`
- budgets spent (`alpha_spent`, `privacy_spent`, `compute_spent`)
- `measurement_transcript_hash`
- `rng_commitment_id`
- `admission_token`

## Verification Rules (Normative)

1. Validate the receipt against `schema/receipt.schema.json`.
2. Recompute `capsule_hash` from the capsule and confirm it matches the receipt.
3. Check that `budgets_spent` are nonnegative and do not exceed the capsule bid.
4. Ensure `epoch_id` is present and non-empty.
5. Ensure `measurement_transcript_hash` and `rng_commitment_id` are present.
6. Ensure `admission_token` has not been seen before in this epoch (replay prevention).

## Signature

Receipts MUST include a signature object with fixed fields (`alg`, `key_id`, `signature_base64`).
Signature verification is an implementation detail at Level-1, but the field structure is normative.

## Extensions (MAY implement)

- Additional signature algorithms or multi-signature envelopes.
- Explicit `receipt_hash` fields for caching.
