# v9_0

> Path: `Genesis/schema/v9_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `acceptance_receipt_v1.jsonschema`: JSON Schema contract.
- `analysis_code_bundle_manifest_v1.jsonschema`: JSON Schema contract.
- `dataset_manifest_v1.jsonschema`: JSON Schema contract.
- `dual_key_override_v1.jsonschema`: JSON Schema contract.
- `rsi_boundless_science_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_daemon_pack_v9.jsonschema`: JSON Schema contract.
- `science_attempt_record_v1.jsonschema`: JSON Schema contract.
- `science_lease_token_v1.jsonschema`: JSON Schema contract.
- `science_ledger_v1.jsonl.schema`: project artifact.
- `science_suitepack_v1.jsonschema`: JSON Schema contract.
- `science_task_spec_v1.jsonschema`: JSON Schema contract.
- `science_toolchain_manifest_v1.jsonschema`: JSON Schema contract.
- `sealed_science_eval_receipt_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 12 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v9_0
find Genesis/schema/v9_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v9_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
