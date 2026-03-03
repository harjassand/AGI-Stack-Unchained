# tests

> Path: `Genesis/genesis/tests`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `conftest.py`: pytest shared fixtures and hooks.
- `test_capsules.py`: Python module or executable script.
- `test_causal_builder.py`: Python module or executable script.
- `test_failure_patterns.py`: Python module or executable script.
- `test_forager.py`: Python module or executable script.
- `test_policy_builder.py`: Python module or executable script.
- `test_promotion.py`: Python module or executable script.
- `test_protocol_budget.py`: Python module or executable script.
- `test_search_loop.py`: Python module or executable script.
- `test_shadow_causal_eval.py`: Python module or executable script.
- `test_shadow_cdel.py`: Python module or executable script.
- `test_shadow_policy_eval.py`: Python module or executable script.
- `test_shadow_system_eval.py`: Python module or executable script.
- `test_shadow_world_model_eval.py`: Python module or executable script.
- `test_system_builder.py`: Python module or executable script.
- `test_world_model_builder.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la Genesis/genesis/tests
find Genesis/genesis/tests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/tests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
