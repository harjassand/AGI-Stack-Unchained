# tests

> Path: `tools/mission_control/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `conftest.py`: pytest shared fixtures and hooks.
- `test_chat_router_v2.py`: Python module or executable script.
- `test_mission_pipeline_v1.py`: Python module or executable script.
- `test_nlpmc_v1.py`: Python module or executable script.
- `test_omega_snapshot.py`: Python module or executable script.
- `test_run_scan.py`: Python module or executable script.
- `test_sas_val_snapshot.py`: Python module or executable script.
- `test_security.py`: Python module or executable script.
- `test_stream_server_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la tools/mission_control/tests
find tools/mission_control/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/mission_control/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
