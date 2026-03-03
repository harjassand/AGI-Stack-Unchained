# cli

> Path: `meta-core/cli`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `meta_core_apply.py`: Python module or executable script.
- `meta_core_audit_active.py`: Python module or executable script.
- `meta_core_canary.py`: Python module or executable script.
- `meta_core_commit.py`: Python module or executable script.
- `meta_core_rollback.py`: Python module or executable script.
- `meta_core_stage.py`: Python module or executable script.
- `meta_core_verify.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la meta-core/cli
find meta-core/cli -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/cli | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
