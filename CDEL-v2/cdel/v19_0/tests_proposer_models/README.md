# tests_proposer_models

> Path: `CDEL-v2/cdel/v19_0/tests_proposer_models`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_arena_ft_agent_dispatch_smoke_v1.py`: Python module or executable script.
- `test_model_bundle_hash_integrity_v1.py`: Python module or executable script.
- `test_model_pointer_atomicity_v1.py`: Python module or executable script.
- `test_runtime_load_fail_closed_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 4 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/tests_proposer_models
find CDEL-v2/cdel/v19_0/tests_proposer_models -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/tests_proposer_models | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
