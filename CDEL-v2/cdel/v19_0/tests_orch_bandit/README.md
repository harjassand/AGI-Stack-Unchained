# tests_orch_bandit

> Path: `CDEL-v2/cdel/v19_0/tests_orch_bandit`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_bandit_bounds_enforced_v1.py`: Python module or executable script.
- `test_bandit_select_determinism_v1.py`: Python module or executable script.
- `test_bandit_update_ewma_v1.py`: Python module or executable script.
- `test_microkernel_bandit_integration_smoke_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 4 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/tests_orch_bandit
find CDEL-v2/cdel/v19_0/tests_orch_bandit -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/tests_orch_bandit | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
