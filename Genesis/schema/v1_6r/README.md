# v1_6r

> Path: `Genesis/schema/v1_6r`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `family_semantics_report_v1.jsonschema`: JSON Schema contract.
- `instance_pack_v1.jsonschema`: JSON Schema contract.
- `instance_witness_index_v1.jsonschema`: JSON Schema contract.
- `instance_witness_v1.jsonschema`: JSON Schema contract.
- `macro_cross_env_support_report_v1.jsonschema`: JSON Schema contract.
- `mech_benchmark_pack_v1.jsonschema`: JSON Schema contract.
- `mech_patch_active_set_v1.jsonschema`: JSON Schema contract.
- `mech_patch_admission_report_v1.jsonschema`: JSON Schema contract.
- `mech_patch_admit_receipt_v1.jsonschema`: JSON Schema contract.
- `mech_patch_eval_cert_v1.jsonschema`: JSON Schema contract.
- `ontology_active_set_v2.jsonschema`: JSON Schema contract.
- `ontology_admit_receipt_v2.jsonschema`: JSON Schema contract.
- `ontology_def_v2.jsonschema`: JSON Schema contract.
- `ontology_eval_report_v2.jsonschema`: JSON Schema contract.
- `ontology_ledger_entry_v2.jsonschema`: JSON Schema contract.
- `ontology_patch_v2.jsonschema`: JSON Schema contract.
- `ontology_snapshot_v2.jsonschema`: JSON Schema contract.
- `rsi_ontology_receipt_v2.jsonschema`: JSON Schema contract.
- `rsi_real_campaign_pack_v2.jsonschema`: JSON Schema contract.
- `rsi_transfer_receipt_v1.jsonschema`: JSON Schema contract.
- `rsi_transfer_window_report_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 21 files

## Operational Checks

```bash
ls -la Genesis/schema/v1_6r
find Genesis/schema/v1_6r -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v1_6r | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
