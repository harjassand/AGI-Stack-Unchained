# val_v17_0

> Path: `orchestrator/val_v17_0`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `coordinator_v17_0.py`: Python module or executable script.

## File-Type Surface

- `py`: 2 files

## Operational Checks

```bash
ls -la orchestrator/val_v17_0
find orchestrator/val_v17_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/val_v17_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
