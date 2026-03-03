# governance

> Path: `orchestrator/omega_v19_0/governance`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `anti_monopoly_gate_v1.py`: Python module or executable script.
- `frontier_lock_v1.py`: Python module or executable script.
- `routing_receipts_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 3 files

## Operational Checks

```bash
ls -la orchestrator/omega_v19_0/governance
find orchestrator/omega_v19_0/governance -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/omega_v19_0/governance | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
