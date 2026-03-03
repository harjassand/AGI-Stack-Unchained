# omega

> Path: `meta-core/stage/bundles/1d278f92aebb77b9f56158504a27bda88e118392aa74bbe4bc7e45d4f716ce14/omega`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `omega_activation_binding_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la meta-core/stage/bundles/1d278f92aebb77b9f56158504a27bda88e118392aa74bbe4bc7e45d4f716ce14/omega
find meta-core/stage/bundles/1d278f92aebb77b9f56158504a27bda88e118392aa74bbe4bc7e45d4f716ce14/omega -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/1d278f92aebb77b9f56158504a27bda88e118392aa74bbe4bc7e45d4f716ce14/omega | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
