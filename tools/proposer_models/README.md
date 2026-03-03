# proposer_models

> Path: `tools/proposer_models`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `pointers_v1.py`: Python module or executable script.
- `runtime_v1.py`: Python module or executable script.
- `store_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 3 files

## Operational Checks

```bash
ls -la tools/proposer_models
find tools/proposer_models -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/proposer_models | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
