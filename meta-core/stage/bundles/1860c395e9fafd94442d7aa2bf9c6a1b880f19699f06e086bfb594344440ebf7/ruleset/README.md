# ruleset

> Path: `meta-core/stage/bundles/1860c395e9fafd94442d7aa2bf9c6a1b880f19699f06e086bfb594344440ebf7/ruleset`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `accept.ir.json`: JSON contract, config, or artifact.
- `costvec.ir.json`: JSON contract, config, or artifact.
- `migrate.ir.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la meta-core/stage/bundles/1860c395e9fafd94442d7aa2bf9c6a1b880f19699f06e086bfb594344440ebf7/ruleset
find meta-core/stage/bundles/1860c395e9fafd94442d7aa2bf9c6a1b880f19699f06e086bfb594344440ebf7/ruleset -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/1860c395e9fafd94442d7aa2bf9c6a1b880f19699f06e086bfb594344440ebf7/ruleset | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
