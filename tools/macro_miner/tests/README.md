# tests

> Path: `tools/macro_miner/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_macro_miner_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 1 files

## Operational Checks

```bash
ls -la tools/macro_miner/tests
find tools/macro_miner/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/macro_miner/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
