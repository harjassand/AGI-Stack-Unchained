# tests

> Path: `tools/genesis_engine/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_ge_bucket_nonfungible_v1.py`: Python module or executable script.
- `test_ge_llm_selector_replay_path_v1.py`: Python module or executable script.
- `test_ge_novelty_laundering_block_v1.py`: Python module or executable script.
- `test_ge_receipt_ingest_scopes_to_daemon_v1.py`: Python module or executable script.
- `test_ge_symbiotic_optimizer_v0_2.py`: Python module or executable script.
- `test_ge_symbiotic_optimizer_v0_3_deterministic.py`: Python module or executable script.
- `test_ge_symbiotic_optimizer_v0_3_skill_policy_v1.py`: Python module or executable script.
- `test_ge_symbiotic_optimizer_v0_3_templates_v1.py`: Python module or executable script.
- `test_ge_xs_snapshot_deterministic_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 9 files

## Operational Checks

```bash
ls -la tools/genesis_engine/tests
find tools/genesis_engine/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/genesis_engine/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
