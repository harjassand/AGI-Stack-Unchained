# proposer

> Path: `agi-orchestrator/orchestrator/proposer`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `agent.py`: Python module or executable script.
- `base.py`: Python module or executable script.
- `llm.py`: Python module or executable script.
- `pyut_repair.py`: Python module or executable script.
- `repair.py`: Python module or executable script.
- `template.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files

## Operational Checks

```bash
ls -la agi-orchestrator/orchestrator/proposer
find agi-orchestrator/orchestrator/proposer -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/orchestrator/proposer | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
