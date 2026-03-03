# tests

> Path: `tools/polymath/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_metal_codegen_v1.py`: Python module or executable script.
- `test_refinery_end_to_end_pubchem_conquer_improves_v1.py`: Python module or executable script.
- `test_refinery_proposer_deterministic_v1.py`: Python module or executable script.
- `test_refinery_proposer_emits_summary_v1.py`: Python module or executable script.
- `test_seed_flagships_idempotent_v1.py`: Python module or executable script.
- `test_void_to_goals_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 6 files

## Operational Checks

```bash
ls -la tools/polymath/tests
find tools/polymath/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/polymath/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
