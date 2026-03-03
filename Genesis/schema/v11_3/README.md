# v11_3

> Path: `Genesis/schema/v11_3`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `arch_allowlist_v1.jsonschema`: JSON Schema contract.
- `arch_eval_config_dev_v1.jsonschema`: JSON Schema contract.
- `arch_eval_config_heldout_v1.jsonschema`: JSON Schema contract.
- `arch_search_config_v1.jsonschema`: JSON Schema contract.
- `arch_synthesis_lease_token_v1.jsonschema`: JSON Schema contract.
- `arch_synthesis_toolchain_manifest_v1.jsonschema`: JSON Schema contract.
- `arch_training_config_v1.jsonschema`: JSON Schema contract.
- `conjecture_archive_index_v1.jsonschema`: JSON Schema contract.
- `q32_v1.jsonschema`: JSON Schema contract.
- `rsi_arch_synthesis_pack_v1.jsonschema`: JSON Schema contract.
- `rsi_sas_math_pack_v1.jsonschema`: JSON Schema contract.
- `sas_arch_build_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_arch_ir_v1.jsonschema`: JSON Schema contract.
- `sas_arch_manifest_v1.jsonschema`: JSON Schema contract.
- `sas_architecture_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_conjecture_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_conjecture_gen_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_conjecture_ir_v1.jsonschema`: JSON Schema contract.
- `sas_conjecture_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_family_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_family_capability_report_v1.jsonschema`: JSON Schema contract.
- `sas_family_registry_v1.jsonschema`: JSON Schema contract.
- `sas_health_report_v1.jsonschema`: JSON Schema contract.
- `sas_ignition_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_math_eval_report_v1.jsonschema`: JSON Schema contract.
- ... and 18 more files.

## File-Type Surface

- `jsonschema`: 40 files
- `schema`: 3 files

## Operational Checks

```bash
ls -la Genesis/schema/v11_3
find Genesis/schema/v11_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v11_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
