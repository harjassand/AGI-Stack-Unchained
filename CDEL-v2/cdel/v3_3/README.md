# v3_3

> Path: `CDEL-v2/cdel/v3_3`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `tests/`: tests and validation assets.

## Key Files

- `__init__.py`: Python module or executable script.
- `barrier_ledger.py`: Python module or executable script.
- `constants.py`: Python module or executable script.
- `immutable_core.py`: Python module or executable script.
- `meta_ledger.py`: Python module or executable script.
- `swarm_ledger.py`: Python module or executable script.
- `verify_rsi_swarm_v4.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v3_3
find CDEL-v2/cdel/v3_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v3_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
