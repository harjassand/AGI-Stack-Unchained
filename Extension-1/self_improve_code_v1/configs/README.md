# configs

> Path: `Extension-1/self_improve_code_v1/configs`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `real_dev.json`: JSON contract, config, or artifact.
- `real_dev_fast.json`: JSON contract, config, or artifact.
- `real_dev_fast_laptop_v1_3.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la Extension-1/self_improve_code_v1/configs
find Extension-1/self_improve_code_v1/configs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/self_improve_code_v1/configs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
