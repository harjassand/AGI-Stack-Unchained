# v3_3

> Path: `Genesis/schema/v3_3`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `bridge_import_manifest_v1.jsonschema`: JSON Schema contract.
- `bridge_import_receipt_v1.jsonschema`: JSON Schema contract.
- `bridge_offer_v1.jsonschema`: JSON Schema contract.
- `meta_block_v1.jsonschema`: JSON Schema contract.
- `meta_ledger_report_v1.jsonschema`: JSON Schema contract.
- `meta_policy_v1.jsonschema`: JSON Schema contract.
- `meta_state_v1.jsonschema`: JSON Schema contract.
- `meta_update_v1.jsonschema`: JSON Schema contract.
- `rsi_real_swarm_pack_v4.jsonschema`: JSON Schema contract.
- `rsi_swarm_receipt_v5.jsonschema`: JSON Schema contract.
- `rsi_swarm_report_v5.jsonschema`: JSON Schema contract.
- `swarm_event_v5.jsonschema`: JSON Schema contract.
- `swarm_graph_report_v2.jsonschema`: JSON Schema contract.
- `swarm_ledger_v5.jsonl.schema`: project artifact.

## File-Type Surface

- `jsonschema`: 13 files
- `schema`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema/v3_3
find Genesis/schema/v3_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/v3_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
