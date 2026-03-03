# tests

> Path: `CDEL-v2/cdel/v1_6r/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_v1_5r_rsi_ignition_regression.py`: Python module or executable script.
- `test_v1_6r_editworld_env_determinism.py`: Python module or executable script.
- `test_v1_6r_editworld_invalid_token_witness.py`: Python module or executable script.
- `test_v1_6r_macro_cross_env_support_report_replay.py`: Python module or executable script.
- `test_v1_6r_mech_patch_eval_cert_replay.py`: Python module or executable script.
- `test_v1_6r_mech_patch_regression_rejected.py`: Python module or executable script.
- `test_v1_6r_ontology_v2_integration.py`: Python module or executable script.
- `test_v1_6r_ontology_v2_unit.py`: Python module or executable script.
- `test_v1_6r_rsi_transfer_positive.py`: Python module or executable script.
- `test_v1_6r_witness_emission_on_invalid_suite_row.py`: Python module or executable script.
- `test_v1_6r_witness_family_replay_property.py`: Python module or executable script.
- `test_v1_6r_witness_family_requires_keyed_ops.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_6r/tests
find CDEL-v2/cdel/v1_6r/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_6r/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
