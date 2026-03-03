# schemas

> Path: `meta-core/meta_constitution/v1/schemas`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `constitution_manifest.schema.json`: JSON contract, config, or artifact.
- `dominance_witness.schema.json`: JSON contract, config, or artifact.
- `migration.schema.json`: JSON contract, config, or artifact.
- `proof_bundle_manifest.schema.json`: JSON contract, config, or artifact.
- `receipt.schema.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 5 files

## Operational Checks

```bash
ls -la meta-core/meta_constitution/v1/schemas
find meta-core/meta_constitution/v1/schemas -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/meta_constitution/v1/schemas | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
