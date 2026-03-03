# kernel

> Path: `meta-core/kernel`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `verifier/`: component subtree.

## Key Files

- `verify_promotion_bundle.py`: Python module or executable script.

## File-Type Surface

- `py`: 1 files

## Operational Checks

```bash
ls -la meta-core/kernel
find meta-core/kernel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/kernel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
