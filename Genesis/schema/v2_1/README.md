# v2_1

> Path: `Genesis/schema/v2_1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `autoconcept_manifest_v1.jsonschema`: JSON Schema contract.
- `opt_concept_patch_v1.jsonschema`: JSON Schema contract.
- `opt_concept_v1.jsonschema`: JSON Schema contract.
- `opt_ontology_active_set_v1.jsonschema`: JSON Schema contract.
- `opt_ontology_ledger_v1.jsonl.schema`: project artifact.
- `rsi_real_demon_campaign_pack_v7.jsonschema`: JSON Schema contract.
- `rsi_real_recursive_ontology_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_recursive_ontology_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_recursive_ontology_report_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 8 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v2_1
find Genesis/schema/v2_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v2_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
