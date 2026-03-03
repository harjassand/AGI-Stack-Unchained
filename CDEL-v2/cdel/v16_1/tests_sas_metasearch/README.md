# tests_sas_metasearch

> Path: `CDEL-v2/cdel/v16_1/tests_sas_metasearch`

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
- `test_bundle_completeness_fail_closed.py`: Python module or executable script.
- `test_metasearch_verifier_uses_worker_batch.py`: Python module or executable script.
- `test_replay_independent_of_campaign_filenames.py`: Python module or executable script.
- `test_rust_binary_pinning.py`: Python module or executable script.
- `test_schema_validator_cache.py`: Python module or executable script.
- `test_selection_receipt_recomputable.py`: Python module or executable script.
- `test_trace_hash_chain_recompute.py`: Python module or executable script.
- `test_v16_baseline_intensity_override_applies.py`: Python module or executable script.
- `test_v16_verifier_passes_with_overrides.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 12 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v16_1/tests_sas_metasearch
find CDEL-v2/cdel/v16_1/tests_sas_metasearch -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v16_1/tests_sas_metasearch | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
