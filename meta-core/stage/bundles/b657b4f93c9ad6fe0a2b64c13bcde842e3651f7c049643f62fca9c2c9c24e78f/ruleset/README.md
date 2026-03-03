# ruleset

> Path: `meta-core/stage/bundles/b657b4f93c9ad6fe0a2b64c13bcde842e3651f7c049643f62fca9c2c9c24e78f/ruleset`

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
ls -la meta-core/stage/bundles/b657b4f93c9ad6fe0a2b64c13bcde842e3651f7c049643f62fca9c2c9c24e78f/ruleset
find meta-core/stage/bundles/b657b4f93c9ad6fe0a2b64c13bcde842e3651f7c049643f62fca9c2c9c24e78f/ruleset -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/b657b4f93c9ad6fe0a2b64c13bcde842e3651f7c049643f62fca9c2c9c24e78f/ruleset | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
