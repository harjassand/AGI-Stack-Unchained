# tests

> Path: `CDEL-v2/cdel/v3_1/tests`

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
- `test_v3_1_event_ref_hash_cycle_break_barrier_accept.py`: Python module or executable script.
- `test_v3_1_event_ref_hash_cycle_break_swarm_end.py`: Python module or executable script.
- `test_v3_1_nonstalling_global_barrier_progress.py`: Python module or executable script.
- `test_v3_1_smoke_recursive_run_valid.py`: Python module or executable script.
- `test_v3_1_stale_base_barrier_update_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_cycle_detected_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_depth_limit_exceeded_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_duplicate_join_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_join_not_ready_retryable.py`: Python module or executable script.
- `test_v3_1_subswarm_node_limit_exceeded_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_parent_link_mismatch_fatal.py`: Python module or executable script.
- `test_v3_1_subswarm_path_traversal_fatal.py`: Python module or executable script.
- `test_v3_1_swarm_ledger_hash_chain_valid.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v3_1/tests
find CDEL-v2/cdel/v3_1/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v3_1/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
