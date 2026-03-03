# v10_0

> Path: `Genesis/schema/v10_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `eval_config_v1.jsonschema`: JSON Schema contract.
- `model_base_manifest_v1.jsonschema`: JSON Schema contract.
- `model_eval_receipt_v1.jsonschema`: JSON Schema contract.
- `model_genesis_ignition_receipt_v1.jsonschema`: JSON Schema contract.
- `model_genesis_lease_token_v1.jsonschema`: JSON Schema contract.
- `model_genesis_ledger_v1.jsonl.schema`: project artifact.
- `model_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `model_weights_bundle_v1.jsonschema`: JSON Schema contract.
- `rsi_model_genesis_pack_v1.jsonschema`: JSON Schema contract.
- `sealed_model_eval_receipt_v1.jsonschema`: JSON Schema contract.
- `sealed_training_receipt_v1.jsonschema`: JSON Schema contract.
- `training_config_v1.jsonschema`: JSON Schema contract.
- `training_corpus_index_v1.jsonschema`: JSON Schema contract.
- `training_corpus_manifest_v1.jsonschema`: JSON Schema contract.
- `training_example_v1.jsonschema`: JSON Schema contract.
- `training_examples_v1.jsonl.schema`: project artifact.
- `training_toolchain_manifest_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 15 files
- `schema`: 2 files

## Operational Checks

```bash
ls -la Genesis/schema/v10_0
find Genesis/schema/v10_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v10_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
