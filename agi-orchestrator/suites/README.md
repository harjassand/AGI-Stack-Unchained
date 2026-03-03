# suites

> Path: `agi-orchestrator/suites`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `agent_reliability_dev_current.json`: JSON contract, config, or artifact.
- `env_dev_current.json`: JSON contract, config, or artifact.
- `env_hard_dev_current.json`: JSON contract, config, or artifact.
- `io_dev_current.json`: JSON contract, config, or artifact.
- `pyut_dev_current.json`: JSON contract, config, or artifact.
- `pyut_transfer_dev_current.json`: JSON contract, config, or artifact.
- `tooluse_dev_current.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 7 files

## Operational Checks

```bash
ls -la agi-orchestrator/suites
find agi-orchestrator/suites -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/suites | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
