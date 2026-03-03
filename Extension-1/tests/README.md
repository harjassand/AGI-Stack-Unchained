# tests

> Path: `Extension-1/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `conftest.py`: pytest shared fixtures and hooks.
- `test_arm_id_stable.py`: Python module or executable script.
- `test_candidate_id_vectors_policy_empty.py`: Python module or executable script.
- `test_edit_apply_byte_stable.py`: Python module or executable script.
- `test_json_canon_bytes.py`: Python module or executable script.
- `test_replay_no_exec_verifies_hashes.py`: Python module or executable script.
- `test_search_order_reproducible.py`: Python module or executable script.
- `test_state_update_reproducible.py`: Python module or executable script.
- `test_tar_deterministic_metadata.py`: Python module or executable script.
- `test_token_locator_single_match.py`: Python module or executable script.
- `test_unified_diff_difflib_stable.py`: Python module or executable script.

## File-Type Surface

- `py`: 11 files

## Operational Checks

```bash
ls -la Extension-1/tests
find Extension-1/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
