# tests

> Path: `CDEL-v2/cdel/v3_3/tests`

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
- `test_v3_3_meta_block_derivation_deterministic.py`: Python module or executable script.
- `test_v3_3_meta_block_includes_exact_epoch_updates.py`: Python module or executable script.
- `test_v3_3_meta_head_declare_mismatch_fatal.py`: Python module or executable script.
- `test_v3_3_meta_latency_violation_fatal.py`: Python module or executable script.
- `test_v3_3_meta_policy_drives_bridge_imports.py`: Python module or executable script.
- `test_v3_3_meta_policy_out_of_bounds_fatal.py`: Python module or executable script.
- `test_v3_3_meta_provenance_requires_valid_result_verify.py`: Python module or executable script.
- `test_v3_3_meta_update_hash_deterministic.py`: Python module or executable script.
- `test_v3_3_smoke_holographic_run_valid.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v3_3/tests
find CDEL-v2/cdel/v3_3/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v3_3/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
