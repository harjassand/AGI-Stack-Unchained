# tests

> Path: `CDEL-v2/cdel/v2_3/tests`

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
- `test_fatal_if_icore_mismatch.py`: Python module or executable script.
- `test_fatal_if_icore_receipt_missing.py`: Python module or executable script.
- `test_hardening_run_requires_attack_rejection_then_accept.py`: Python module or executable script.
- `test_immutable_core_lock_hashing_stable.py`: Python module or executable script.
- `test_meta_core_receipt_schema_and_hash.py`: Python module or executable script.
- `test_reject_patch_touching_icore_file.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v2_3/tests
find CDEL-v2/cdel/v2_3/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v2_3/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
