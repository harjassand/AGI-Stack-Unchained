# v4_0

> Path: `Genesis/schema/v4_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `grand_challenge_suite_manifest_v1.jsonschema`: JSON Schema contract.
- `omega_checkpoint_receipt_v1.jsonschema`: JSON Schema contract.
- `omega_ignition_receipt_v1.jsonschema`: JSON Schema contract.
- `omega_ledger_v1.jsonl.schema`: project artifact.
- `omega_run_report_v1.jsonschema`: JSON Schema contract.
- `rsi_real_omega_pack_v1.jsonschema`: JSON Schema contract.
- `sealed_task_v2.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 6 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v4_0
find Genesis/schema/v4_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v4_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
