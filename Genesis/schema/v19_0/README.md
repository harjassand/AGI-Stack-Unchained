# v19_0

> Path: `Genesis/schema/v19_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `action_kind_enum_v1.jsonschema`: JSON Schema contract.
- `anti_monopoly_state_v1.jsonschema`: JSON Schema contract.
- `arena_candidate_precheck_receipt_v1.jsonschema`: JSON Schema contract.
- `arena_candidate_v1.jsonschema`: JSON Schema contract.
- `arena_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `arena_surrogate_eval_receipt_v1.jsonschema`: JSON Schema contract.
- `axis_gate_failure_v1.jsonschema`: JSON Schema contract.
- `axis_specific_proof_pclp_v1.jsonschema`: JSON Schema contract.
- `axis_upgrade_bundle_v1.jsonschema`: JSON Schema contract.
- `backrefute_cert_v1.jsonschema`: JSON Schema contract.
- `benchmark_run_receipt_v2.jsonschema`: JSON Schema contract.
- `benchmark_suite_manifest_v1.jsonschema`: JSON Schema contract.
- `benchmark_suite_set_v1.jsonschema`: JSON Schema contract.
- `budget_spec_v1.jsonschema`: JSON Schema contract.
- `candidate_campaign_ids_list_v1.jsonschema`: JSON Schema contract.
- `candidate_precheck_receipt_v1.jsonschema`: JSON Schema contract.
- `cert_invariance_contract_v1.jsonschema`: JSON Schema contract.
- `constitution_kernel_profile_v1.jsonschema`: JSON Schema contract.
- `constitution_morphism_v1.jsonschema`: JSON Schema contract.
- `constructor_conservativity_cert_v1.jsonschema`: JSON Schema contract.
- `continuity_constitution_v1.jsonschema`: JSON Schema contract.
- `continuity_morphism_v1.jsonschema`: JSON Schema contract.
- `continuity_receipt_v1.jsonschema`: JSON Schema contract.
- `coordinator_isa_program_v1.jsonschema`: JSON Schema contract.
- `coordinator_opcode_table_v1.jsonschema`: JSON Schema contract.
- ... and 170 more files.

## File-Type Surface

- `jsonschema`: 195 files

## Operational Checks

```bash
ls -la Genesis/schema/v19_0
find Genesis/schema/v19_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v19_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
