# scripts

> Path: `agi-orchestrator/scripts`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `aggregate_scoreboards.py`: Python module or executable script.
- `capstone_ae_validation.sh`: shell automation script.
- `check_repo_policy.py`: Python module or executable script.
- `check_suite_integrity.py`: Python module or executable script.
- `check_suite_quality_gate.py`: Python module or executable script.
- `dev_bootstrap.sh`: shell automation script.
- `export_completion_bundle.py`: Python module or executable script.
- `export_completion_bundle.sh`: shell automation script.
- `generate_pyut_heldout_candidate_suite.py`: Python module or executable script.
- `mine_and_augment_pyut_dev_suite.py`: Python module or executable script.
- `preflight.py`: Python module or executable script.
- `run_orchestrator.py`: Python module or executable script.
- `smoke_orchestrator_e2e.sh`: shell automation script.
- `smoke_orchestrator_env_agent_e2e.sh`: shell automation script.
- `smoke_orchestrator_env_e2e.sh`: shell automation script.
- `smoke_orchestrator_env_hard_uplift.sh`: shell automation script.
- `smoke_orchestrator_io_e2e.sh`: shell automation script.
- `smoke_orchestrator_io_with_mock_llm.sh`: shell automation script.
- `smoke_orchestrator_io_with_mock_llm_retry.sh`: shell automation script.
- `smoke_orchestrator_io_with_replay_backend.sh`: shell automation script.
- `smoke_orchestrator_llm_budget_exceeded.sh`: shell automation script.
- `smoke_orchestrator_pyut_with_replay_backend.sh`: shell automation script.
- `smoke_orchestrator_tooluse_agent_e2e.sh`: shell automation script.
- `smoke_orchestrator_tooluse_safety_negative.sh`: shell automation script.
- `smoke_orchestrator_tooluse_safety_positive.sh`: shell automation script.
- ... and 4 more files.

## File-Type Surface

- `sh`: 17 files
- `py`: 12 files

## Operational Checks

```bash
ls -la agi-orchestrator/scripts
find agi-orchestrator/scripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/scripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
