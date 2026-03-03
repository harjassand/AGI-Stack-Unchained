# ruleset

> Path: `meta-core/stage/bundles/23b3a9b55fdd04f150127c1b0cb64844970e130a83c6ba71af523147c023802c/ruleset`

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
ls -la meta-core/stage/bundles/23b3a9b55fdd04f150127c1b0cb64844970e130a83c6ba71af523147c023802c/ruleset
find meta-core/stage/bundles/23b3a9b55fdd04f150127c1b0cb64844970e130a83c6ba71af523147c023802c/ruleset -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/23b3a9b55fdd04f150127c1b0cb64844970e130a83c6ba71af523147c023802c/ruleset | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
