# v1

> Path: `meta-core/meta_constitution/v1`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `schemas/`: schema contracts and data models.
- `spec/`: component subtree.

## Key Files

- `META_HASH`: project artifact.
- `build_meta_hash.sh`: shell automation script.

## File-Type Surface

- `sh`: 1 files
- `(no_ext)`: 1 files

## Operational Checks

```bash
ls -la meta-core/meta_constitution/v1
find meta-core/meta_constitution/v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/meta_constitution/v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
