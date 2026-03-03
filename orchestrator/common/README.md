# common

> Path: `orchestrator/common`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `canonical_json_v1.py`: Python module or executable script.
- `eudrs_u_bootstrap_producer_v1.py`: Python module or executable script.
- `eudrs_u_dmpl_phase4_producer_v1.py`: Python module or executable script.
- `hash_chain_v1.py`: Python module or executable script.
- `run_invoker_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 5 files

## Operational Checks

```bash
ls -la orchestrator/common
find orchestrator/common -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/common | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
