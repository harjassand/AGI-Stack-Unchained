# tests

> Path: `Extension-1/self_improve_code_v1/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `conftest.py`: pytest shared fixtures and hooks.
- `test_attempt_loop_produces_valid_patch_when_available.py`: Python module or executable script.
- `test_autocalibration_selects_failing_tier.py`: Python module or executable script.
- `test_devscreen_eval_set_deterministic.py`: Python module or executable script.
- `test_fail_signature_stable.py`: Python module or executable script.
- `test_filter_report_schema_and_reject_reason.py`: Python module or executable script.
- `test_flagship_config_load.py`: Python module or executable script.
- `test_flagship_smoke_2epochs.py`: Python module or executable script.
- `test_identity_candidate_applies_cleanly.py`: Python module or executable script.
- `test_min_eligible_per_epoch_behavior.py`: Python module or executable script.
- `test_null_control_forces_escalation.py`: Python module or executable script.
- `test_partial_run_verify_ok.py`: Python module or executable script.
- `test_patch_templates_deterministic.py`: Python module or executable script.
- `test_scoreboard_canonical.py`: Python module or executable script.
- `test_selection_deterministic.py`: Python module or executable script.
- `test_semantic_noop_detector.py`: Python module or executable script.
- `test_submission_policy_distance_reducers.py`: Python module or executable script.

## File-Type Surface

- `py`: 17 files

## Operational Checks

```bash
ls -la Extension-1/self_improve_code_v1/tests
find Extension-1/self_improve_code_v1/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/self_improve_code_v1/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
