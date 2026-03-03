# rsi_arch_synthesis_v11_0

> Path: `campaigns/rsi_arch_synthesis_v11_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `arch_allowlist_v1.json`: JSON contract, config, or artifact.
- `arch_eval_config_dev_v1.json`: JSON contract, config, or artifact.
- `arch_eval_config_heldout_v1.json`: JSON contract, config, or artifact.
- `arch_search_config_v1.json`: JSON contract, config, or artifact.
- `arch_synthesis_lease_token_v1.json`: JSON contract, config, or artifact.
- `arch_synthesis_toolchain_manifest_v1.json`: JSON contract, config, or artifact.
- `arch_training_config_v1.json`: JSON contract, config, or artifact.
- `rsi_arch_synthesis_pack_v1.json`: JSON contract, config, or artifact.
- `sha256_259dba7133a21eb0f0c32306be99a3dd443f65e1e758928e78a6970bc878cbf6.sas_opset_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_9b01e142c03bd765d8f2233e92008669da21be92cc9b41e3373bf664923c1120.sas_family_registry_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 10 files

## Operational Checks

```bash
ls -la campaigns/rsi_arch_synthesis_v11_0
find campaigns/rsi_arch_synthesis_v11_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_arch_synthesis_v11_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
