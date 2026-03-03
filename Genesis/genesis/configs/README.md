# configs

> Path: `Genesis/genesis/configs`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `baselines.json`: JSON contract, config, or artifact.
- `causal_v1_3.json`: JSON contract, config, or artifact.
- `datasets.json`: JSON contract, config, or artifact.
- `default.json`: JSON contract, config, or artifact.
- `policy.json`: JSON contract, config, or artifact.
- `policy_envs.json`: JSON contract, config, or artifact.
- `system.json`: JSON contract, config, or artifact.
- `system_v0_7.json`: JSON contract, config, or artifact.
- `system_v0_8.json`: JSON contract, config, or artifact.
- `system_v0_9.json`: JSON contract, config, or artifact.
- `system_v1_0.json`: JSON contract, config, or artifact.
- `system_v1_1.json`: JSON contract, config, or artifact.
- `system_v1_2.json`: JSON contract, config, or artifact.
- `world_model.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 14 files

## Operational Checks

```bash
ls -la Genesis/genesis/configs
find Genesis/genesis/configs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/configs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
