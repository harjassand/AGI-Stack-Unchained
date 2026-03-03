# tests

> Path: `CDEL-v2/cdel/v3_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `conftest.py`: pytest shared fixtures and hooks.
- `test_agent_attempts_to_write_barrier_ledger_rejected.py`: Python module or executable script.
- `test_agent_icore_mismatch_fatal.py`: Python module or executable script.
- `test_barrier_ledger_crosslink_required.py`: Python module or executable script.
- `test_commit_policy_round_commit_deterministic.py`: Python module or executable script.
- `test_swarm_ledger_hash_chain_valid.py`: Python module or executable script.
- `test_swarm_ledger_missing_artifact_fatal.py`: Python module or executable script.
- `test_swarm_smoke_run_valid.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v3_0/tests
find CDEL-v2/cdel/v3_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v3_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
