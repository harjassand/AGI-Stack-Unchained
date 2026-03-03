# configs

> Path: `agi-orchestrator/configs`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sealed_agent_reliability_dev.toml`: TOML configuration.
- `sealed_agent_reliability_heldout.toml`: TOML configuration.
- `sealed_env_dev.toml`: TOML configuration.
- `sealed_env_hard_dev.toml`: TOML configuration.
- `sealed_env_hard_heldout.toml`: TOML configuration.
- `sealed_env_heldout.toml`: TOML configuration.
- `sealed_env_safety_dev.toml`: TOML configuration.
- `sealed_env_safety_heldout.toml`: TOML configuration.
- `sealed_io_dev.toml`: TOML configuration.
- `sealed_io_heldout.toml`: TOML configuration.
- `sealed_pyut_dev.toml`: TOML configuration.
- `sealed_pyut_heldout.toml`: TOML configuration.
- `sealed_pyut_transfer_dev.toml`: TOML configuration.
- `sealed_pyut_transfer_heldout.toml`: TOML configuration.
- `sealed_tooluse_dev.toml`: TOML configuration.
- `sealed_tooluse_heldout.toml`: TOML configuration.
- `sealed_tooluse_safety_dev.toml`: TOML configuration.
- `sealed_tooluse_safety_heldout.toml`: TOML configuration.

## File-Type Surface

- `toml`: 18 files

## Operational Checks

```bash
ls -la agi-orchestrator/configs
find agi-orchestrator/configs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/configs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
