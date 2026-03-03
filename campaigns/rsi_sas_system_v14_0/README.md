# rsi_sas_system_v14_0

> Path: `campaigns/rsi_sas_system_v14_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `rsi_sas_system_pack_v1.json`: JSON contract, config, or artifact.
- `sas_system_policy_v1.json`: JSON contract, config, or artifact.
- `sas_system_suitepack_dev_v1.json`: JSON contract, config, or artifact.
- `sas_system_suitepack_heldout_stub_v1.json`: JSON contract, config, or artifact.
- `sas_system_target_catalog_v1.json`: JSON contract, config, or artifact.
- `sas_system_toolchain_manifest_lean_v1.json`: JSON contract, config, or artifact.
- `sas_system_toolchain_manifest_py_v1.json`: JSON contract, config, or artifact.
- `sas_system_toolchain_manifest_rust_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_system_v14_0
find campaigns/rsi_sas_system_v14_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_system_v14_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
