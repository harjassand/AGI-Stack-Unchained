# v13_0

> Path: `Genesis/schema/v13_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `q32_v1.jsonschema`: JSON Schema contract.
- `sas_science_candidate_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_science_dataset_manifest_v1.jsonschema`: JSON Schema contract.
- `sas_science_dataset_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_science_eval_report_v1.jsonschema`: JSON Schema contract.
- `sas_science_fit_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_science_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_science_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_science_split_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_science_theory_ir_v1.jsonschema`: JSON Schema contract.
- `sealed_science_eval_receipt_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 11 files

## Operational Checks

```bash
ls -la Genesis/schema/v13_0
find Genesis/schema/v13_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v13_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
