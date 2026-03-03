# tests

> Path: `CDEL-v2/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ccai_x_v1/`: component subtree.
- `fixtures/`: deterministic fixture data.
- `v1_5r/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `conftest.py`: pytest shared fixtures and hooks.
- `test_adoption_constraints.py`: Python module or executable script.
- `test_aggregate_runs.py`: Python module or executable script.
- `test_alias_lint.py`: Python module or executable script.
- `test_audit_markers.py`: Python module or executable script.
- `test_backfill_skips_invalid.py`: Python module or executable script.
- `test_cache_equivalence_from_run.py`: Python module or executable script.
- `test_cache_equivalence_minimal.py`: Python module or executable script.
- `test_capacity_exhaustion.py`: Python module or executable script.
- `test_claims_normalization_does_not_mask_semantic_diff.py`: Python module or executable script.
- `test_claims_skip_semantics.py`: Python module or executable script.
- `test_cli_contract.py`: Python module or executable script.
- `test_commit_atomicity.py`: Python module or executable script.
- `test_curriculum_generator.py`: Python module or executable script.
- `test_curriculum_subset.py`: Python module or executable script.
- `test_deps_exact_match.py`: Python module or executable script.
- `test_determinism_end_to_end.py`: Python module or executable script.
- `test_enum_reuse_mode.py`: Python module or executable script.
- `test_enum_solves_seed_tasks.py`: Python module or executable script.
- `test_experiment_audit.py`: Python module or executable script.
- `test_fuzz_rejections.py`: Python module or executable script.
- `test_hash_changes_on_semantic_change.py`: Python module or executable script.
- `test_hash_stability_same_semantics.py`: Python module or executable script.
- `test_invariants_bundle.py`: Python module or executable script.
- ... and 36 more files.

## File-Type Surface

- `py`: 61 files

## Operational Checks

```bash
ls -la CDEL-v2/tests
find CDEL-v2/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
