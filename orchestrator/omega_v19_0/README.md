# omega_v19_0

> Path: `orchestrator/omega_v19_0`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `governance/`: component subtree.
- `orch_bandit/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `coordinator_v1.py`: Python module or executable script.
- `eval_cadence_v1.py`: Python module or executable script.
- `goal_synthesizer_v1.py`: Python module or executable script.
- `microkernel_v1.py`: Python module or executable script.
- `mission_goal_ingest_v1.py`: Python module or executable script.
- `policy_vm_v1.py`: Python module or executable script.
- `promoter_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la orchestrator/omega_v19_0
find orchestrator/omega_v19_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/omega_v19_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
