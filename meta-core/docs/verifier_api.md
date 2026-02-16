# Verifier CLI API

## Command

```
verifier verify \
  --bundle-dir <path> \
  --parent-bundle-dir <path_or_empty> \
  --meta-dir <path_to_meta_constitution_v1> \
  --out <path_to_receipt.json>
```

## Exit codes

- `0` only if the receipt verdict is `VALID`.
- `2` if the receipt verdict is `INVALID`.
- `1` only for verifier internal errors (still writes a receipt with reason `KERNEL_INTERNAL_ERROR`).

## Receipt format

The receipt is GCJ-1 canonical JSON with these required fields:

- `format`: `"meta_core_receipt_v1"`
- `schema_version`: `"1"`
- `verdict`: `"VALID"` or `"INVALID"`
- `bundle_hash`: hex64
- `meta_hash`: hex64
- `kernel_hash`: hex64
- `reason_code`: string (always present; `"OK"` if VALID)
- `details`: object (always present; empty ok)

## Reason codes (non-exhaustive)

- `OK`
- `MANIFEST_SCHEMA_INVALID`
- `BLOB_HASH_MISMATCH`
- `BUNDLE_HASH_MISMATCH`
- `RULESET_HASH_MISMATCH`
- `META_HASH_MISMATCH`
- `KERNEL_HASH_MISMATCH`
- `IR_PARSE_ERROR`
- `IR_STATIC_CHECK_FAILED`
- `IR_RUNTIME_ERROR`
- `GAS_LIMIT_EXCEEDED`
- `PROOF_BUNDLE_INVALID`
- `DOMINANCE_CHECK_FAILED`
- `MIGRATION_FAILED`
- `KERNEL_INTERNAL_ERROR`
