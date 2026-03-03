# v3_1

> Path: `Genesis/schema/v3_1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `barrier_entry_v3.jsonschema`: JSON Schema contract.
- `barrier_ledger_v3.jsonl.schema`: project artifact.
- `rsi_real_swarm_pack_v2.jsonschema`: JSON Schema contract.
- `rsi_swarm_receipt_v2.jsonschema`: JSON Schema contract.
- `rsi_swarm_report_v2.jsonschema`: JSON Schema contract.
- `subswarm_export_bundle_v1.jsonschema`: JSON Schema contract.
- `subswarm_parent_link_v1.jsonschema`: JSON Schema contract.
- `swarm_event_v2.jsonschema`: JSON Schema contract.
- `swarm_ledger_v2.jsonl.schema`: project artifact.
- `swarm_result_manifest_v2.jsonschema`: JSON Schema contract.
- `swarm_task_spec_v2.jsonschema`: JSON Schema contract.
- `swarm_tree_report_v1.jsonschema`: JSON Schema contract.

## File-Type Surface

- `jsonschema`: 10 files
- `schema`: 2 files

## Operational Checks

```bash
ls -la Genesis/schema/v3_1
find Genesis/schema/v3_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v3_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
