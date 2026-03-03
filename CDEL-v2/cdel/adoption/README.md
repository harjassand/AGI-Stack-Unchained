# adoption

> Path: `CDEL-v2/cdel/adoption`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `canon.py`: Python module or executable script.
- `storage.py`: Python module or executable script.
- `verifier.py`: Python module or executable script.

## File-Type Surface

- `py`: 4 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/adoption
find CDEL-v2/cdel/adoption -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/adoption | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
