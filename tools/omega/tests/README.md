# tests

> Path: `tools/omega/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_benchmark_emits_gate_json_v1.py`: Python module or executable script.
- `test_benchmark_gate_json_contains_gate_f_details_v1.py`: Python module or executable script.
- `test_benchmark_gate_p_uses_scout_subruns_v1.py`: Python module or executable script.
- `test_capability_registry_prod_parity_v1.py`: Python module or executable script.
- `test_capability_usage_artifact_d6_v1.py`: Python module or executable script.
- `test_ek_meta_verify_v1.py`: Python module or executable script.
- `test_gate_f_non_regression_v1.py`: Python module or executable script.
- `test_gate_loader_prefers_json_v1.py`: Python module or executable script.
- `test_gate_proof_determinism_d4_v1.py`: Python module or executable script.
- `test_ge_sh1_state_dir_rel_points_to_subrun_root_v1.py`: Python module or executable script.
- `test_goal_synthesizer_promo_focus_d6_v1.py`: Python module or executable script.
- `test_llm_router_replay_and_parse_d7_v1.py`: Python module or executable script.
- `test_omega_skill_manifest_v1.py`: Python module or executable script.
- `test_overnight_runner_capability_frontier_v1.py`: Python module or executable script.
- `test_overnight_runner_defaults_polymath_store_root_refinery_v1.py`: Python module or executable script.
- `test_overnight_runner_gate_a_warmup_v1.py`: Python module or executable script.
- `test_overnight_runner_ge_artifact_count_v1.py`: Python module or executable script.
- `test_overnight_runner_llm_router_integration_d7_v1.py`: Python module or executable script.
- `test_overnight_runner_materialize_submodules_v1.py`: Python module or executable script.
- `test_overnight_runner_polymath_failfast_d3_v1.py`: Python module or executable script.
- `test_overnight_runner_preflight_fail_d4_v1.py`: Python module or executable script.
- `test_overnight_runner_profile_refinery_v1.py`: Python module or executable script.
- `test_overnight_runner_profile_unified_v1.py`: Python module or executable script.
- `test_overnight_runner_rollback_metadata_v1.py`: Python module or executable script.
- `test_overnight_runner_sh1_scaffold_overlay_v1.py`: Python module or executable script.
- ... and 10 more files.

## File-Type Surface

- `py`: 35 files

## Operational Checks

```bash
ls -la tools/omega/tests
find tools/omega/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
