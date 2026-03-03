# v17_0

> Path: `Genesis/schema/v17_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `kernel_hotloop_report_v1.jsonschema`: JSON Schema contract.
- `meta_core_promo_verify_receipt_v1.jsonschema`: JSON Schema contract.
- `microkernel_task_v1.jsonschema`: JSON Schema contract.
- `rsi_sas_val_pack_v17_0.jsonschema`: JSON Schema contract.
- `sas_val_policy_v1.jsonschema`: JSON Schema contract.
- `sas_val_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `v16_1_smoke_receipt_v1.jsonschema`: JSON Schema contract.
- `val_benchmark_report_v1.jsonschema`: JSON Schema contract.
- `val_decoded_trace_v1.jsonschema`: JSON Schema contract.
- `val_equivalence_receipt_v1.jsonschema`: JSON Schema contract.
- `val_exec_backend_v1.jsonschema`: JSON Schema contract.
- `val_exec_trace_v1.jsonschema`: JSON Schema contract.
- `val_lift_ir_v1.jsonschema`: JSON Schema contract.
- `val_patch_manifest_v1.jsonschema`: JSON Schema contract.
- `val_safety_receipt_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 15 files

## Operational Checks

```bash
ls -la Genesis/schema/v17_0
find Genesis/schema/v17_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v17_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
