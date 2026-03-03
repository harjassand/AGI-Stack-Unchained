# v16_1

> Path: `Genesis/schema/v16_1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `metasearch_build_receipt_v1.jsonschema`: JSON Schema contract.
- `metasearch_compute_report_v1.jsonschema`: JSON Schema contract.
- `metasearch_eval_trace_v1.jsonschema`: JSON Schema contract.
- `metasearch_eval_trace_v2.jsonschema`: JSON Schema contract.
- `metasearch_plan_v1.jsonschema`: JSON Schema contract.
- `metasearch_prior_v1.jsonschema`: JSON Schema contract.
- `metasearch_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `metasearch_trace_corpus_suitepack_v1.jsonschema`: JSON Schema contract.
- `rsi_sas_metasearch_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_sas_metasearch_pack_v16_1.jsonschema`: JSON Schema contract.
- `sas_metasearch_policy_v1.jsonschema`: JSON Schema contract.
- `sas_metasearch_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_metasearch_promotion_bundle_v2.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 13 files

## Operational Checks

```bash
ls -la Genesis/schema/v16_1
find Genesis/schema/v16_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v16_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
