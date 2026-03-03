# scripts

> Path: `meta-core/scripts`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `build.sh`: shell automation script.
- `compute_toolchain_root.py`: Python module or executable script.
- `smoke_orchestration.sh`: shell automation script.
- `smoke_test.sh`: shell automation script.

## File-Type Surface

- `sh`: 3 files
- `py`: 1 files

## Operational Checks

```bash
ls -la meta-core/scripts
find meta-core/scripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/scripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
