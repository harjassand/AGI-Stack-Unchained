# v12_0

> Path: `Genesis/schema/v12_0`

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
- `sas_code_attempt_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_code_candidate_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_code_eval_report_v1.jsonschema`: JSON Schema contract.
- `sas_code_gen_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_code_ir_v1.jsonschema`: JSON Schema contract.
- `sas_code_perf_report_v1.jsonschema`: JSON Schema contract.
- `sas_code_problem_spec_v1.jsonschema`: JSON Schema contract.
- `sas_code_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_code_selection_receipt_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 10 files

## Operational Checks

```bash
ls -la Genesis/schema/v12_0
find Genesis/schema/v12_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v12_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
