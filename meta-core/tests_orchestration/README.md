# tests_orchestration

> Path: `meta-core/tests_orchestration`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_apply_and_audit.py`: Python module or executable script.
- `test_apply_determinism.py`: Python module or executable script.
- `test_atomicity_simulated_failure.py`: Python module or executable script.
- `test_dmpl_phase4_promotion_bundle.py`: Python module or executable script.
- `test_ledger_entries.py`: Python module or executable script.
- `test_regime_upgrade_gate.py`: Python module or executable script.
- `test_reject_does_not_mutate_active.py`: Python module or executable script.
- `test_v19_wiring_smoke.py`: Python module or executable script.
- `test_verify_promotion_bundle_wrapper.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la meta-core/tests_orchestration
find meta-core/tests_orchestration -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/tests_orchestration | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
