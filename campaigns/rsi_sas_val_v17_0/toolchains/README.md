# toolchains

> Path: `campaigns/rsi_sas_val_v17_0/toolchains`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `pinned_rust_toolchain.sh`: shell automation script.
- `pinned_val_runner.sh`: shell automation script.
- `toolchain_manifest_rust_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_val_runner_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `sh`: 2 files
- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_val_v17_0/toolchains
find campaigns/rsi_sas_val_v17_0/toolchains -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_val_v17_0/toolchains | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
