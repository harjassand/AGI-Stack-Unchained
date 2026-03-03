# v15_0

> Path: `Genesis/schema/v15_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `capability_registry_v2.jsonschema`: JSON Schema contract.
- `fixture_matrix_v1.jsonschema`: JSON Schema contract.
- `immutable_tree_snapshot_v1.jsonschema`: JSON Schema contract.
- `kernel_activation_receipt_v1.jsonschema`: JSON Schema contract.
- `kernel_equiv_report_v1.jsonschema`: JSON Schema contract.
- `kernel_ledger_entry_v1.jsonschema`: JSON Schema contract.
- `kernel_perf_report_v1.jsonschema`: JSON Schema contract.
- `kernel_plan_ir_v1.jsonschema`: JSON Schema contract.
- `kernel_policy_v1.jsonschema`: JSON Schema contract.
- `kernel_run_receipt_v1.jsonschema`: JSON Schema contract.
- `kernel_run_spec_v1.jsonschema`: JSON Schema contract.
- `kernel_trace_event_v1.jsonschema`: JSON Schema contract.
- `suitepack_v1.jsonschema`: JSON Schema contract.
- `toolchain_manifest_v15.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 14 files

## Operational Checks

```bash
ls -la Genesis/schema/v15_0
find Genesis/schema/v15_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v15_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
