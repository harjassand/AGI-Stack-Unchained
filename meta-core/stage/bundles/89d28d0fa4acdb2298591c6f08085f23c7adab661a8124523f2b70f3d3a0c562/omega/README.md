# omega

> Path: `meta-core/stage/bundles/89d28d0fa4acdb2298591c6f08085f23c7adab661a8124523f2b70f3d3a0c562/omega`

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
ls -la meta-core/stage/bundles/89d28d0fa4acdb2298591c6f08085f23c7adab661a8124523f2b70f3d3a0c562/omega
find meta-core/stage/bundles/89d28d0fa4acdb2298591c6f08085f23c7adab661a8124523f2b70f3d3a0c562/omega -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/89d28d0fa4acdb2298591c6f08085f23c7adab661a8124523f2b70f3d3a0c562/omega | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
