# rsi_model_genesis_v10_0

> Path: `campaigns/rsi_model_genesis_v10_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `eval_config_v1.json`: JSON contract, config, or artifact.
- `math_train_allowlist_v1.json`: JSON contract, config, or artifact.
- `model_base_manifest_v1.json`: JSON contract, config, or artifact.
- `model_genesis_lease_token_v1.json`: JSON contract, config, or artifact.
- `rsi_model_genesis_pack_v1.json`: JSON contract, config, or artifact.
- `training_config_v1.json`: JSON contract, config, or artifact.
- `training_toolchain_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 7 files

## Operational Checks

```bash
ls -la campaigns/rsi_model_genesis_v10_0
find campaigns/rsi_model_genesis_v10_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_model_genesis_v10_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
