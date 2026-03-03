# engine

> Path: `meta-core/engine`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `activation.py`: Python module or executable script.
- `apply.py`: Python module or executable script.
- `atomic_fs.py`: Python module or executable script.
- `audit.py`: Python module or executable script.
- `constants.py`: Python module or executable script.
- `errors.py`: Python module or executable script.
- `gcj1_min.py`: Python module or executable script.
- `hashing.py`: Python module or executable script.
- `ledger.py`: Python module or executable script.
- `regime_upgrade.py`: Python module or executable script.
- `store.py`: Python module or executable script.
- `verifier_client.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la meta-core/engine
find meta-core/engine -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/engine | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
