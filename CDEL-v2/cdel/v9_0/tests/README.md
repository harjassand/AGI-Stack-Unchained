# tests

> Path: `CDEL-v2/cdel/v9_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_v9_0_acceptance_requires_replication.py`: Python module or executable script.
- `test_v9_0_denies_write_control.py`: Python module or executable script.
- `test_v9_0_denies_write_env_leases.py`: Python module or executable script.
- `test_v9_0_denies_write_leases.py`: Python module or executable script.
- `test_v9_0_env_drift_invalid.py`: Python module or executable script.
- `test_v9_0_hazard_gating_enforced.py`: Python module or executable script.
- `test_v9_0_network_used_invalid.py`: Python module or executable script.
- `test_v9_0_requires_enable_boundless_science.py`: Python module or executable script.
- `test_v9_0_requires_valid_lease.py`: Python module or executable script.
- `test_v9_0_stale_space_path_normalization.py`: Python module or executable script.
- `test_v9_0_vector_allowlist_enforced.py`: Python module or executable script.
- `test_v9_0_zero_attempt_valid.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 14 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v9_0/tests
find CDEL-v2/cdel/v9_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v9_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
