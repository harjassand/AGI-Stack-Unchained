# redteam_patches

> Path: `campaigns/rsi_sas_val_v17_0/redteam_patches`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `patch_blr.bin`: project artifact.
- `patch_br.bin`: project artifact.
- `patch_infinite_loop.bin`: project artifact.
- `patch_oob_load_blocks.bin`: project artifact.
- `patch_oob_store_state.bin`: project artifact.
- `patch_self_modify_attempt.bin`: project artifact.
- `patch_sp_write.bin`: project artifact.
- `patch_svc.bin`: project artifact.
- `patch_uses_x16.bin`: project artifact.
- `redteam_expectations_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `bin`: 9 files
- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_val_v17_0/redteam_patches
find campaigns/rsi_sas_val_v17_0/redteam_patches -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_val_v17_0/redteam_patches | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
