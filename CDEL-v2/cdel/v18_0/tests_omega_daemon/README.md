# tests_omega_daemon

> Path: `CDEL-v2/cdel/v18_0/tests_omega_daemon`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `test_actionseq_apply_v1.py`: Python module or executable script.
- `test_actionseq_legality_v1.py`: Python module or executable script.
- `test_actionseq_obligation_v1.py`: Python module or executable script.
- `test_activation_bundle_contains_binding_blob.py`: Python module or executable script.
- `test_activation_bundle_copy_isolation.py`: Python module or executable script.
- `test_activation_bundle_hashes_accept_by_meta_core_stage.py`: Python module or executable script.
- `test_activation_changes_active_manifest_hash.py`: Python module or executable script.
- `test_activation_requires_meta_core_receipt.py`: Python module or executable script.
- `test_authority_hash_deterministic_v1.py`: Python module or executable script.
- `test_bid_market_math_and_tiebreak_v1.py`: Python module or executable script.
- `test_budget_exhaustion_blocks_dispatch.py`: Python module or executable script.
- `test_campaign_ge_sh1_emits_ccap_bundle_v1.py`: Python module or executable script.
- `test_campaign_ge_sh1_patch_registry_detection_v1.py`: Python module or executable script.
- `test_ccap_apply_uses_dispatch_repo_root_v1.py`: Python module or executable script.
- `test_ccap_budget_unification_v1.py`: Python module or executable script.
- `test_ccap_patch_acceptance_v1.py`: Python module or executable script.
- `test_ccap_refutation_enum_sync_v1.py`: Python module or executable script.
- `test_ccap_replace_file_patch_v1.py`: Python module or executable script.
- `test_ccap_rollout_registry_v1.py`: Python module or executable script.
- `test_ccap_runtime_repo_tree_tolerant_stable_v1.py`: Python module or executable script.
- `test_ccap_runtime_tracked_files_submodule_filter_v1.py`: Python module or executable script.
- `test_ccap_schema_validation_v1.py`: Python module or executable script.
- `test_ccap_score_runs_on_workspace_v1.py`: Python module or executable script.
- `test_composite_benchmark_runner_v1.py`: Python module or executable script.
- ... and 120 more files.

## File-Type Surface

- `py`: 145 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v18_0/tests_omega_daemon
find CDEL-v2/cdel/v18_0/tests_omega_daemon -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v18_0/tests_omega_daemon | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
