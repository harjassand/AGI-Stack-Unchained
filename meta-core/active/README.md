# active

> Path: `meta-core/active`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ledger/`: runtime state and persistence artifacts.
- `tmp/`: component subtree.
- `work/`: component subtree.

## Key Files

- `ACTIVE_BUNDLE`: project artifact.
- `ACTIVE_NEXT_BUNDLE`: project artifact.
- `LOCK`: project artifact.
- `PREV_ACTIVE_BUNDLE`: project artifact.

## File-Type Surface

- `(no_ext)`: 4 files

## Operational Checks

```bash
ls -la meta-core/active
find meta-core/active -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/active | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
