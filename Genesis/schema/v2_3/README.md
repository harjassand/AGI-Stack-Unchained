# v2_3

> Path: `Genesis/schema/v2_3`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `hardening_ledger_v1.jsonl.schema`: project artifact.
- `immutable_core_lock_v1.jsonschema`: JSON Schema contract.
- `immutable_core_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_demon_receipt_v9.jsonschema`: JSON Schema contract.
- `rsi_hardening_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_hardening_report_v1.jsonschema`: JSON Schema contract.
- `rsi_real_demon_campaign_pack_v9.jsonschema`: JSON Schema contract.
- `rsi_real_hardening_pack_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 7 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v2_3
find Genesis/schema/v2_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v2_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
