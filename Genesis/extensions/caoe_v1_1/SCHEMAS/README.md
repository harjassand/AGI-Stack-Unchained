# SCHEMAS

> Path: `Genesis/extensions/caoe_v1_1/SCHEMAS`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `candidate_manifest_v1_1.json`: JSON contract, config, or artifact.
- `evidence_report_v1_1.json`: JSON contract, config, or artifact.
- `intervention_log_v1_1.json`: JSON contract, config, or artifact.
- `lifecycle_state_v1_1.json`: JSON contract, config, or artifact.
- `macro_do_event_v1_1.json`: JSON contract, config, or artifact.
- `mechanism_registry_diff_v1_1.json`: JSON contract, config, or artifact.
- `mechanism_registry_v1_1.json`: JSON contract, config, or artifact.
- `ontology_patch_v1_1.json`: JSON contract, config, or artifact.
- `ontology_spec_v1_1.json`: JSON contract, config, or artifact.
- `receipt_v1_1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 10 files

## Operational Checks

```bash
ls -la Genesis/extensions/caoe_v1_1/SCHEMAS
find Genesis/extensions/caoe_v1_1/SCHEMAS -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/extensions/caoe_v1_1/SCHEMAS | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
