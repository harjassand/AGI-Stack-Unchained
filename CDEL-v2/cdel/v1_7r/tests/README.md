# tests

> Path: `CDEL-v2/cdel/v1_7r/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `.gitkeep`: project artifact.
- `__init__.py`: Python module or executable script.
- `test_macros_v2_guarded_encoder_exact.py`: Python module or executable script.
- `test_macros_v2_mdl_gain_exact.py`: Python module or executable script.
- `test_ontology_v3_dl_metric_exact.py`: Python module or executable script.
- `test_ontology_v3_training_determinism.py`: Python module or executable script.
- `test_rsi_real_demon_v3_integration.py`: Python module or executable script.
- `test_trace_v2_context_hash_rule.py`: Python module or executable script.
- `test_v1_7r_causalworld_determinism.py`: Python module or executable script.
- `test_v1_7r_eval_causalworld_basic.py`: Python module or executable script.
- `test_v1_7r_eval_wmworld_basic.py`: Python module or executable script.
- `test_v1_7r_generators_determinism.py`: Python module or executable script.
- `test_v1_7r_macro_cross_env_support_v2_recompute.py`: Python module or executable script.
- `test_v1_7r_mech_patch_eval_cert_sci_recompute.py`: Python module or executable script.
- `test_v1_7r_nontriviality_gate_wmworld.py`: Python module or executable script.
- `test_v1_7r_rational_codec.py`: Python module or executable script.
- `test_v1_7r_rsi_science_positive.py`: Python module or executable script.
- `test_v1_7r_science_witness_replay_property.py`: Python module or executable script.
- `test_v1_7r_singular_matrix_witness.py`: Python module or executable script.
- `test_v1_7r_suite_row_validation_fail_closed.py`: Python module or executable script.
- `test_v1_7r_wmworld_determinism.py`: Python module or executable script.

## File-Type Surface

- `py`: 20 files
- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_7r/tests
find CDEL-v2/cdel/v1_7r/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_7r/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
