# v14_0

> Path: `Genesis/schema/v14_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `active_system_snapshot_v1.jsonschema`: JSON Schema contract.
- `capability_registry_v1.jsonschema`: JSON Schema contract.
- `rsi_sas_system_pack_v1.jsonschema`: JSON Schema contract.
- `sas_science_workmeter_job_v1.jsonschema`: JSON Schema contract.
- `sas_science_workmeter_out_v1.jsonschema`: JSON Schema contract.
- `sas_system_candidate_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_system_component_registry_v1.jsonschema`: JSON Schema contract.
- `sas_system_equivalence_report_v1.jsonschema`: JSON Schema contract.
- `sas_system_immutable_tree_snapshot_v1.jsonschema`: JSON Schema contract.
- `sas_system_ir_v1.jsonschema`: JSON Schema contract.
- `sas_system_ledger_event_v1.jsonschema`: JSON Schema contract.
- `sas_system_perf_report_v1.jsonschema`: JSON Schema contract.
- `sas_system_policy_v1.jsonschema`: JSON Schema contract.
- `sas_system_profile_report_v1.jsonschema`: JSON Schema contract.
- `sas_system_promotion_bundle_v1.jsonschema`: JSON Schema contract.
- `sas_system_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `sas_system_suitepack_v1.jsonschema`: JSON Schema contract.
- `sas_system_target_catalog_v1.jsonschema`: JSON Schema contract.
- `sas_system_toolchain_manifest_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 19 files

## Operational Checks

```bash
ls -la Genesis/schema/v14_0
find Genesis/schema/v14_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v14_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
