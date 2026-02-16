# ge_config_v1

SH-1 GE-side untrusted configuration for deterministic receipt ingest, PD/XS derivation, bucket planning, hard-avoid projection, and novelty thresholds.

- `ge_config_id` is content-addressed as `sha256(canonical_json(config_with_zero_id))`.
- `bucket_fracs_q32` must sum to `2^32` exactly.
- Receipt ingest globs are deterministic (`path.as_posix()` sort).
- Hard-avoid and novelty are derived from receipts only.
- Proposal space is PATCH-only and template-enumerated (`CODE_FASTPATH_GUARD`, `JSON_TWEAK_COOLDOWN_MINUS_1`, `JSON_TWEAK_BUDGET_HINT_MINUS_1STEP`).
