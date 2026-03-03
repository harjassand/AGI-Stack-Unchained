# inputs

> Path: `campaigns/rsi_real_swarm_v3_2/inputs`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `child_swarm_inputs_v2.json`: JSON contract, config, or artifact.
- `problem_barrier_1.json`: JSON contract, config, or artifact.
- `problem_child_1.json`: JSON contract, config, or artifact.
- `problem_root_spawn_c1.json`: JSON contract, config, or artifact.
- `problem_root_spawn_c2.json`: JSON contract, config, or artifact.
- `problem_spawn_1.json`: JSON contract, config, or artifact.
- `swarm_inputs_v2.json`: JSON contract, config, or artifact.
- `swarm_inputs_v3.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_swarm_v3_2/inputs
find campaigns/rsi_real_swarm_v3_2/inputs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_swarm_v3_2/inputs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
