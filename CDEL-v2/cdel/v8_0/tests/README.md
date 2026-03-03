# tests

> Path: `CDEL-v2/cdel/v8_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_v8_0_accept_requires_pass_receipt.py`: Python module or executable script.
- `test_v8_0_budget_enforced.py`: Python module or executable script.
- `test_v8_0_meta_drift_fail_closed.py`: Python module or executable script.
- `test_v8_0_offline_only.py`: Python module or executable script.
- `test_v8_0_prefix_valid_running.py`: Python module or executable script.
- `test_v8_0_spoofed_receipt_rejected.py`: Python module or executable script.
- `test_v8_0_stale_space_path_normalization.py`: Python module or executable script.
- `test_v8_0_toolchain_pin_required.py`: Python module or executable script.
- `test_v8_0_two_key_required.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 11 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v8_0/tests
find CDEL-v2/cdel/v8_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v8_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
