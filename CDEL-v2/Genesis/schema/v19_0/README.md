# v19_0

> Path: `CDEL-v2/Genesis/schema/v19_0`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `anti_monopoly_state_v1.jsonschema`: JSON Schema contract.
- `arena_candidate_precheck_receipt_v1.jsonschema`: JSON Schema contract.
- `arena_candidate_v1.jsonschema`: JSON Schema contract.
- `arena_selection_receipt_v1.jsonschema`: JSON Schema contract.
- `arena_surrogate_eval_receipt_v1.jsonschema`: JSON Schema contract.
- `dependency_debt_state_v1.jsonschema`: JSON Schema contract.
- `dependency_routing_receipt_v1.jsonschema`: JSON Schema contract.
- `extension_queued_receipt_v1.jsonschema`: JSON Schema contract.
- `long_run_preflight_summary_v1.jsonschema`: JSON Schema contract.
- `mission_compile_receipt_v1.jsonschema`: JSON Schema contract.
- `mission_evidence_pack_v1.jsonschema`: JSON Schema contract.
- `mission_graph_v1.jsonschema`: JSON Schema contract.
- `mission_input_manifest_v1.jsonschema`: JSON Schema contract.
- `mission_intent_graph_v1.jsonschema`: JSON Schema contract.
- `mission_node_result_v1.jsonschema`: JSON Schema contract.
- `mission_state_v1.jsonschema`: JSON Schema contract.
- `native_metal_build_proof_v1.jsonschema`: JSON Schema contract.
- `native_metal_healthcheck_receipt_v1.jsonschema`: JSON Schema contract.
- `native_metal_healthcheck_vectors_v1.jsonschema`: JSON Schema contract.
- `native_metal_src_merkle_v1.jsonschema`: JSON Schema contract.
- `oracle_hidden_tests_pack_v1.jsonschema`: JSON Schema contract.
- `oracle_operator_bank_pointer_v1.jsonschema`: JSON Schema contract.
- `oracle_operator_bank_v1.jsonschema`: JSON Schema contract.
- `oracle_operator_mining_receipt_v1.jsonschema`: JSON Schema contract.
- `oracle_program_ast_v1.jsonschema`: JSON Schema contract.
- ... and 40 more files.

## File-Type Surface

- `jsonschema`: 65 files

## Operational Checks

```bash
ls -la CDEL-v2/Genesis/schema/v19_0
find CDEL-v2/Genesis/schema/v19_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/Genesis/schema/v19_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
