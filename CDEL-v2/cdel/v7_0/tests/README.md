# tests

> Path: `CDEL-v2/cdel/v7_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_v7_0_boundless_locked_without_enable.py`: Python module or executable script.
- `test_v7_0_clearance_threshold_crossmultiply.py`: Python module or executable script.
- `test_v7_0_decision_deterministic.py`: Python module or executable script.
- `test_v7_0_meta_drift_pauses.py`: Python module or executable script.
- `test_v7_0_missing_decision_fail.py`: Python module or executable script.
- `test_v7_0_network_any_denied.py`: Python module or executable script.
- `test_v7_0_policy_hash_lock.py`: Python module or executable script.
- `test_v7_0_run_verifier_binds_actions_to_decisions.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v7_0/tests
find CDEL-v2/cdel/v7_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v7_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
