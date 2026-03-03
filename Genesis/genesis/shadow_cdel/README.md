# shadow_cdel

> Path: `Genesis/genesis/shadow_cdel`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `baseline_registry.py`: Python module or executable script.
- `calibration.py`: Python module or executable script.
- `dataset_registry.py`: Python module or executable script.
- `forager.py`: Python module or executable script.
- `lcb.py`: Python module or executable script.
- `nontriviality.py`: Python module or executable script.
- `policy_env_registry.py`: Python module or executable script.
- `shadow_causal_eval.py`: Python module or executable script.
- `shadow_eval.py`: Python module or executable script.
- `shadow_policy_eval.py`: Python module or executable script.
- `shadow_system_eval.py`: Python module or executable script.
- `shadow_world_model_eval.py`: Python module or executable script.

## File-Type Surface

- `py`: 13 files

## Operational Checks

```bash
ls -la Genesis/genesis/shadow_cdel
find Genesis/genesis/shadow_cdel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/shadow_cdel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
