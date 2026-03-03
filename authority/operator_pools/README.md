# operator_pools

> Path: `authority/operator_pools`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `op_active_set_v1.json`: JSON contract, config, or artifact.
- `op_pool_v1.json`: JSON contract, config, or artifact.
- `operator_pool_core_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la authority/operator_pools
find authority/operator_pools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/operator_pools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
