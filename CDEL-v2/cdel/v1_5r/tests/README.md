# tests

> Path: `CDEL-v2/cdel/v1_5r/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_learnability_gate_v1_5r.py`: Python module or executable script.
- `test_portfolio_generator_determinism_v1_5r.py`: Python module or executable script.
- `test_provenance_reports_v1_5r.py`: Python module or executable script.
- `test_rho_barrier_reports_v1_5r.py`: Python module or executable script.
- `test_v1_5r_family_semantics_rejects_signature_only.py`: Python module or executable script.
- `test_v1_5r_family_semantics_requires_key_sensitivity_for_insertions.py`: Python module or executable script.
- `test_v1_5r_meta_patch_translation_positive.py`: Python module or executable script.
- `test_v1_5r_meta_patch_translation_rejects_semantic_change.py`: Python module or executable script.
- `test_v1_5r_portfolio_requires_two_envs.py`: Python module or executable script.
- `test_v1_5r_rsi_integrity_budget_stability_fail.py`: Python module or executable script.
- `test_v1_5r_rsi_integrity_positive.py`: Python module or executable script.
- `test_v1_5r_rsi_integrity_requires_mined_rho.py`: Python module or executable script.
- `test_v1_5r_rsi_integrity_requires_nontrivial_recovery.py`: Python module or executable script.
- `test_v1_5r_rsi_portfolio_positive.py`: Python module or executable script.
- `test_v1_5r_signature_mismatch_rejected.py`: Python module or executable script.
- `test_v1_5r_verify_rsi_integrity_replay.py`: Python module or executable script.
- `test_witness_ledger_v1_5r.py`: Python module or executable script.

## File-Type Surface

- `py`: 17 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_5r/tests
find CDEL-v2/cdel/v1_5r/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_5r/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
