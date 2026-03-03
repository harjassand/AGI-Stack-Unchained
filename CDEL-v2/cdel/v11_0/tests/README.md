# tests

> Path: `CDEL-v2/cdel/v11_0/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_v11_0_absolute_path_forbidden.py`: Python module or executable script.
- `test_v11_0_allowlist_violation.py`: Python module or executable script.
- `test_v11_0_capacity_eff_mismatch.py`: Python module or executable script.
- `test_v11_0_fingerprint_mismatch.py`: Python module or executable script.
- `test_v11_0_heldout_leak.py`: Python module or executable script.
- `test_v11_0_missing_enable.py`: Python module or executable script.
- `test_v11_0_missing_training_ledger_head.py`: Python module or executable script.
- `test_v11_0_non_q32_value.py`: Python module or executable script.
- `test_v11_0_novelty_mismatch.py`: Python module or executable script.
- `test_v11_0_opset_drift.py`: Python module or executable script.
- `test_v11_0_param_budget_exceeded.py`: Python module or executable script.
- `test_v11_0_root_canon_mismatch.py`: Python module or executable script.
- `test_v11_0_training_network_used.py`: Python module or executable script.
- `test_v11_0_valid_prefix.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v11_0/tests
find CDEL-v2/cdel/v11_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v11_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
