# tests

> Path: `CDEL-v2/cdel/v1_8r/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_ctx_hash_cache_v1_correctness.py`: Python module or executable script.
- `test_ctx_hash_cache_v1_fifo_eviction_determinism.py`: Python module or executable script.
- `test_rsi_real_demon_v4_integration.py`: Python module or executable script.
- `test_translation_validation_workvec_improves.py`: Python module or executable script.

## File-Type Surface

- `py`: 4 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_8r/tests
find CDEL-v2/cdel/v1_8r/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_8r/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
