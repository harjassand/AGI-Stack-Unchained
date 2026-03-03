# ledger

> Path: `CDEL-v2/cdel/ledger`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `alias.py`: Python module or executable script.
- `audit.py`: Python module or executable script.
- `closure.py`: Python module or executable script.
- `errors.py`: Python module or executable script.
- `index.py`: Python module or executable script.
- `lint.py`: Python module or executable script.
- `rebuild.py`: Python module or executable script.
- `stats.py`: Python module or executable script.
- `storage.py`: Python module or executable script.
- `verifier.py`: Python module or executable script.

## File-Type Surface

- `py`: 11 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/ledger
find CDEL-v2/cdel/ledger -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/ledger | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
