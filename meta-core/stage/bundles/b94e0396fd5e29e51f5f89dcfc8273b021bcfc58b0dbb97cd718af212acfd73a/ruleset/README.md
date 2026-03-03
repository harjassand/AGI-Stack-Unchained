# ruleset

> Path: `meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a/ruleset`

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
ls -la meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a/ruleset
find meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a/ruleset -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a/ruleset | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
