# envs

> Path: `CDEL-v2/cdel/v1_7r/envs`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `.gitkeep`: project artifact.
- `__init__.py`: Python module or executable script.
- `causalworld_v1.py`: Python module or executable script.
- `wmworld_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 3 files
- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_7r/envs
find CDEL-v2/cdel/v1_7r/envs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_7r/envs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
