# omega_v18_0

> Path: `orchestrator/omega_v18_0`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `applier_v1.py`: Python module or executable script.
- `clock_v1.py`: Python module or executable script.
- `coordinator_v1.py`: Python module or executable script.
- `decider_v1.py`: Python module or executable script.
- `diagnoser_v1.py`: Python module or executable script.
- `dispatcher_v1.py`: Python module or executable script.
- `goal_synthesizer_v1.py`: Python module or executable script.
- `io_v1.py`: Python module or executable script.
- `locks_v1.py`: Python module or executable script.
- `observer_v1.py`: Python module or executable script.
- `promoter_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la orchestrator/omega_v18_0
find orchestrator/omega_v18_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/omega_v18_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
