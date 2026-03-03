# tests

> Path: `CDEL-v2/cdel/v2_2/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `conftest.py`: pytest shared fixtures and hooks.
- `test_autocodepatch_enum_v1_rank_exhausted.py`: Python module or executable script.
- `test_code_patch_rejects_forbidden_imports.py`: Python module or executable script.
- `test_code_patch_rejects_forbidden_paths.py`: Python module or executable script.
- `test_csi_bench_output_hash_match_required.py`: Python module or executable script.
- `test_csi_double_run_determinism.py`: Python module or executable script.
- `test_csi_tree_hash_deterministic.py`: Python module or executable script.
- `test_full_csi_attempt_passes_with_lru_cache_patch.py`: Python module or executable script.
- `test_outer_csi_run_valid.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v2_2/tests
find CDEL-v2/cdel/v2_2/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v2_2/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
