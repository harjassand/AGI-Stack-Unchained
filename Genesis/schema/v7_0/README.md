# v7_0

> Path: `Genesis/schema/v7_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `alignment_checkpoint_receipt_v1.jsonschema`: JSON Schema contract.
- `alignment_clearance_receipt_v1.jsonschema`: JSON Schema contract.
- `alignment_report_v1.jsonschema`: JSON Schema contract.
- `rsi_alignment_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_daemon_pack_v7.jsonschema`: JSON Schema contract.
- `superego_action_request_v1.jsonschema`: JSON Schema contract.
- `superego_decision_receipt_v1.jsonschema`: JSON Schema contract.
- `superego_ledger_v1.jsonl.schema`: project artifact.
- `superego_policy_lock_v1.jsonschema`: JSON Schema contract.
- `superego_policy_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 9 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v7_0
find Genesis/schema/v7_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v7_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
