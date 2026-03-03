# capsules

> Path: `Genesis/genesis/capsules`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `schema/`: schema contracts and data models.

## Key Files

- `__init__.py`: Python module or executable script.
- `budget.py`: Python module or executable script.
- `canonicalize.py`: Python module or executable script.
- `causal_model_builder.py`: Python module or executable script.
- `causal_witness.py`: Python module or executable script.
- `policy_builder.py`: Python module or executable script.
- `receipt.py`: Python module or executable script.
- `seed_capsule.json`: JSON contract, config, or artifact.
- `system_builder.py`: Python module or executable script.
- `validate.py`: Python module or executable script.
- `world_model_builder.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files
- `json`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/capsules
find Genesis/genesis/capsules -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/capsules | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
