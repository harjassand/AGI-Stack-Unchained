# harnesses

> Path: `CDEL-v2/cdel/sealed/harnesses`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `base.py`: Python module or executable script.
- `env_v1.py`: Python module or executable script.
- `io_v1.py`: Python module or executable script.
- `pyut_v1.py`: Python module or executable script.
- `suite_v1.py`: Python module or executable script.
- `tooluse_v1.py`: Python module or executable script.
- `toy_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/sealed/harnesses
find CDEL-v2/cdel/sealed/harnesses -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/sealed/harnesses | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
