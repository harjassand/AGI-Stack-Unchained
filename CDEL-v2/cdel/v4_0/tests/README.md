# tests

> Path: `CDEL-v2/cdel/v4_0/tests`

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
- `test_v4_0_accel_index_v1_cross_mult_no_floats.py`: Python module or executable script.
- `test_v4_0_checkpoint_receipt_recompute_exact.py`: Python module or executable script.
- `test_v4_0_new_solves_over_baseline_computed_exact.py`: Python module or executable script.
- `test_v4_0_omega_ledger_hash_chain_deterministic.py`: Python module or executable script.
- `test_v4_0_reject_partial_epoch_on_stop.py`: Python module or executable script.
- `test_v4_0_root_path_collision_rejected.py`: Python module or executable script.
- `test_v4_0_sealed_receipt_leak_fields_rejected.py`: Python module or executable script.
- `test_v4_0_sealed_worker_index_invariance.py`: Python module or executable script.
- `test_v4_0_smoke_omega_run_self_improvement_accepts_promotion_valid.py`: Python module or executable script.
- `test_v4_0_smoke_omega_run_two_checkpoints_valid.py`: Python module or executable script.
- `test_v4_0_unbounded_epochs_prefix_verify_stops_at_omega_stop.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 14 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v4_0/tests
find CDEL-v2/cdel/v4_0/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v4_0/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
