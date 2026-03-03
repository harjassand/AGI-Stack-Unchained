# v18_0

> Path: `CDEL-v2/Genesis/schema/v18_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `abstraction_ladder_manifest_v1.jsonschema`: JSON Schema contract.
- `actionseq_v1.jsonschema`: JSON Schema contract.
- `authority_state_v1.jsonschema`: JSON Schema contract.
- `benchmark_run_receipt_v2.jsonschema`: JSON Schema contract.
- `benchmark_suite_manifest_v1.jsonschema`: JSON Schema contract.
- `benchmark_suite_set_v1.jsonschema`: JSON Schema contract.
- `bid_market_state_v1.jsonschema`: JSON Schema contract.
- `bid_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `bid_set_v1.jsonschema`: JSON Schema contract.
- `bid_settlement_receipt_v1.jsonschema`: JSON Schema contract.
- `bid_v1.jsonschema`: JSON Schema contract.
- `bucket_pages_index_v1.jsonschema`: JSON Schema contract.
- `cac_v1.jsonschema`: JSON Schema contract.
- `candidate_syntax_error_v1.jsonschema`: JSON Schema contract.
- `ccap_receipt_v1.jsonschema`: JSON Schema contract.
- `ccap_refutation_cert_v1.jsonschema`: JSON Schema contract.
- `ccap_v1.jsonschema`: JSON Schema contract.
- `concept_bank_manifest_v1.jsonschema`: JSON Schema contract.
- `concept_def_v1.jsonschema`: JSON Schema contract.
- `cooldown_ledger_v1.jsonschema`: JSON Schema contract.
- `determinism_cert_v1.jsonschema`: JSON Schema contract.
- `dmpl_action_receipt_v1.jsonschema`: JSON Schema contract.
- `dmpl_cac_pack_v1.jsonschema`: JSON Schema contract.
- `dmpl_concept_shard_v1.jsonschema`: JSON Schema contract.
- `dmpl_config_v1.jsonschema`: JSON Schema contract.
- ... and 149 more files.

## File-Type Surface

- `jsonschema`: 173 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/Genesis/schema/v18_0
find CDEL-v2/Genesis/schema/v18_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/Genesis/schema/v18_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
