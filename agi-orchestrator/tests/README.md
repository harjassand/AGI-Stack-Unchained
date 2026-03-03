# tests

> Path: `agi-orchestrator/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `conftest.py`: pytest shared fixtures and hooks.
- `test_agent_proposer_tooluse.py`: Python module or executable script.
- `test_agent_solve_deterministic.py`: Python module or executable script.
- `test_agent_solve_writes_plan_skill.py`: Python module or executable script.
- `test_agent_transcript_logs_hashes.py`: Python module or executable script.
- `test_aggregate_scoreboards_deterministic.py`: Python module or executable script.
- `test_capstone_includes_env_hard_metrics.py`: Python module or executable script.
- `test_cdel_client_allows_empty_output_when_file_written.py`: Python module or executable script.
- `test_cdel_client_fails_if_expected_file_missing.py`: Python module or executable script.
- `test_cdel_client_smoke.py`: Python module or executable script.
- `test_check_repo_policy_blocks_large_suite.py`: Python module or executable script.
- `test_check_suite_integrity_fails_on_heldout_bytes_committed.py`: Python module or executable script.
- `test_check_suite_integrity_passes.py`: Python module or executable script.
- `test_concept_registry_loads_and_hashes.py`: Python module or executable script.
- `test_concept_retrieval_topk.py`: Python module or executable script.
- `test_context_pack_deterministic.py`: Python module or executable script.
- `test_context_pack_has_no_paths_or_secrets.py`: Python module or executable script.
- `test_context_pack_includes_spec_hints.py`: Python module or executable script.
- `test_context_pack_truncation_is_stable.py`: Python module or executable script.
- `test_counterexample_capture_io.py`: Python module or executable script.
- `test_domain_resolution_without_cdel_repo.py`: Python module or executable script.
- `test_embedding_deterministic.py`: Python module or executable script.
- `test_env_agent_fallback_when_plan_skill_fails.py`: Python module or executable script.
- `test_env_agent_uses_plan_skill_when_available.py`: Python module or executable script.
- `test_env_smoke_config_materialization_preserves_episodes.py`: Python module or executable script.
- ... and 43 more files.

## File-Type Surface

- `py`: 68 files

## Operational Checks

```bash
ls -la agi-orchestrator/tests
find agi-orchestrator/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
