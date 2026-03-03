# v1_7r

> Path: `Genesis/schema/v1_7r`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `.gitkeep`: project artifact.
- `macro_active_set_v2.jsonschema`: JSON Schema contract.
- `macro_admit_receipt_v2.jsonschema`: JSON Schema contract.
- `macro_def_v2.jsonschema`: JSON Schema contract.
- `macro_eval_report_v2.jsonschema`: JSON Schema contract.
- `macro_ledger_entry_v2.jsonl.schema`: project artifact.
- `ontology_active_set_v3.jsonschema`: JSON Schema contract.
- `ontology_admit_receipt_v3.jsonschema`: JSON Schema contract.
- `ontology_def_v3.jsonschema`: JSON Schema contract.
- `ontology_eval_report_v3.jsonschema`: JSON Schema contract.
- `ontology_ledger_entry_v3.jsonl.schema`: project artifact.
- `ontology_snapshot_v3.jsonschema`: JSON Schema contract.
- `rsi_demon_receipt_v3.jsonschema`: JSON Schema contract.
- `rsi_real_demon_campaign_pack_v3.jsonschema`: JSON Schema contract.
- `trace_event_v2.jsonl.schema`: project artifact.

## File-Type Surface

- `jsonschema`: 11 files
- `schema`: 3 files
- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v1_7r
find Genesis/schema/v1_7r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v1_7r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
