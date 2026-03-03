# tests_sas_science

> Path: `CDEL-v2/cdel/v13_0/tests_sas_science`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_holdout_leak_prevention.py`: Python module or executable script.
- `test_negative_dataset_constant_velocity_not_newton.py`: Python module or executable script.
- `test_negative_dataset_hooke_not_newton.py`: Python module or executable script.
- `test_negative_dataset_inverse_cube_not_newton.py`: Python module or executable script.
- `test_newton_always_output_detection.py`: Python module or executable script.
- `test_noisy_planetary_still_newton.py`: Python module or executable script.
- `test_rejects_lookup_table_constants.py`: Python module or executable script.
- `test_rejects_time_index_memorization.py`: Python module or executable script.
- `test_replay_sealed_eval_match.py`: Python module or executable script.
- `test_schema_rejects_cheat_nodes.py`: Python module or executable script.
- `test_schema_validator_cache.py`: Python module or executable script.
- `test_science_verifier_uses_worker_not_per_eval_subprocess.py`: Python module or executable script.
- `test_sealed_eval_worker_matches_cli_single_job.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v13_0/tests_sas_science
find CDEL-v2/cdel/v13_0/tests_sas_science -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v13_0/tests_sas_science | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
