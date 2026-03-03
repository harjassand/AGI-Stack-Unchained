# rsi_omega_native_module_v0_1

> Path: `campaigns/rsi_omega_native_module_v0_1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `native_module_optimizer_config_v1.json`: JSON contract, config, or artifact.
- `rsi_omega_native_module_pack_v0_1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_rust_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la campaigns/rsi_omega_native_module_v0_1
find campaigns/rsi_omega_native_module_v0_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_omega_native_module_v0_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
