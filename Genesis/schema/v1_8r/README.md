# v1_8r

> Path: `Genesis/schema/v1_8r`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `meta_patch_active_set_v1.jsonschema`: JSON Schema contract.
- `meta_patch_admit_receipt_v1.jsonschema`: JSON Schema contract.
- `meta_patch_def_v1.jsonschema`: JSON Schema contract.
- `meta_patch_eval_report_v1.jsonschema`: JSON Schema contract.
- `meta_patch_ledger_entry_v1.jsonl.schema`: project artifact.
- `rsi_demon_receipt_v4.jsonschema`: JSON Schema contract.
- `rsi_real_demon_campaign_pack_v4.jsonschema`: JSON Schema contract.
- `translation_case_output_v1.jsonschema`: JSON Schema contract.
- `translation_inputs_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 8 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v1_8r
find Genesis/schema/v1_8r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v1_8r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
