# rsi_proposer_arena_micdrop_v1

> Path: `campaigns/rsi_proposer_arena_micdrop_v1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `proposer_arena_agent_registry_v1.json`: JSON contract, config, or artifact.
- `proposer_arena_spec_v1.json`: JSON contract, config, or artifact.
- `proposer_arena_surrogate_policy_v1.json`: JSON contract, config, or artifact.
- `proposer_arena_task_distribution_v1.json`: JSON contract, config, or artifact.
- `rsi_proposer_arena_pack_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 5 files

## Operational Checks

```bash
ls -la campaigns/rsi_proposer_arena_micdrop_v1
find campaigns/rsi_proposer_arena_micdrop_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_proposer_arena_micdrop_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
