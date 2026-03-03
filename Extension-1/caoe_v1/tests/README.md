# tests

> Path: `Extension-1/caoe_v1/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `test_absop_only_v1.py`: Python module or executable script.
- `test_candidate_tar_determinism_v1.py`: Python module or executable script.
- `test_canon_vectors_v1_1.py`: Python module or executable script.
- `test_cinv_wcs_matches_per_regime_min_v1_1.py`: Python module or executable script.
- `test_end_to_end_epoch_with_stub_cdel_v1.py`: Python module or executable script.
- `test_enumerator_generates_lambda_get_v1_1.py`: Python module or executable script.
- `test_enumerator_generates_phi_slice_v1_1.py`: Python module or executable script.
- `test_guided_program_order_determinism_v1_2.py`: Python module or executable script.
- `test_macro_duration_accounting_v1_2.py`: Python module or executable script.
- `test_no_heldout_read_v1.py`: Python module or executable script.
- `test_operator_filters_const_phi_v1_1.py`: Python module or executable script.
- `test_oracles_nuisance_k2_v1_2.py`: Python module or executable script.
- `test_phi_outputs_not_constant_x4.py`: Python module or executable script.
- `test_regression_guard_v1_1.py`: Python module or executable script.
- `test_retest_injection_gated_v1_1.py`: Python module or executable script.
- `test_state_update_determinism_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la Extension-1/caoe_v1/tests
find Extension-1/caoe_v1/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/caoe_v1/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
