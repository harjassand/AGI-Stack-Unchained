# tests

> Path: `CDEL-v2/cdel/v6_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_v6_0_checkpoint_binds_head.py`: Python module or executable script.
- `test_v6_0_ledger_hashchain.py`: Python module or executable script.
- `test_v6_0_meta_drift_fail_closed.py`: Python module or executable script.
- `test_v6_0_prefix_valid_running.py`: Python module or executable script.
- `test_v6_0_restart_resume_tick_monotone.py`: Python module or executable script.
- `test_v6_0_single_instance_lock.py`: Python module or executable script.
- `test_v6_0_stop_pause_controls.py`: Python module or executable script.
- `test_v6_0_tail_truncation_only_incomplete_line.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v6_0/tests
find CDEL-v2/cdel/v6_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v6_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
