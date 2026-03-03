# tests

> Path: `CDEL-v2/cdel/v3_2/tests`

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
- `test_v3_2_barrier_bridge_stale_context_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_blob_hash_mismatch_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_duplicate_accept_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_icore_mismatch_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_import_requires_local_copy_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_offer_hash_mismatch_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_offer_id_hash_deterministic.py`: Python module or executable script.
- `test_v3_2_bridge_publisher_not_valid_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_unverified_export_fatal.py`: Python module or executable script.
- `test_v3_2_bridge_wrong_root_fatal.py`: Python module or executable script.
- `test_v3_2_graph_report_matches_edges.py`: Python module or executable script.
- `test_v3_2_smoke_lateral_run_valid.py`: Python module or executable script.
- `utils.py`: Python module or executable script.

## File-Type Surface

- `py`: 15 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v3_2/tests
find CDEL-v2/cdel/v3_2/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v3_2/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
