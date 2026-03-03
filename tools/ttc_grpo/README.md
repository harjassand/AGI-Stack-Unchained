# ttc_grpo

> Path: `tools/ttc_grpo`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `candidate_store_v1.py`: Python module or executable script.
- `dmpl_eval_harness_v1.py`: Python module or executable script.
- `grpo_config_v1.py`: Python module or executable script.
- `grpo_policy_mlx_v1.py`: Python module or executable script.
- `grpo_runner_v1.py`: Python module or executable script.
- `ir_generator_v1.py`: Python module or executable script.
- `schemas.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la tools/ttc_grpo
find tools/ttc_grpo -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/ttc_grpo | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
