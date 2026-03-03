# rsi_sas_code_v12_0

> Path: `campaigns/rsi_sas_code_v12_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `baseline_bubble_sort_v1.sas_code_ir_v1.json`: JSON contract, config, or artifact.
- `rsi_sas_code_pack_v1.json`: JSON contract, config, or artifact.
- `sas_code_gen_config_v1.json`: JSON contract, config, or artifact.
- `sas_code_lease_token_v1.json`: JSON contract, config, or artifact.
- `sas_code_perf_policy_v1.json`: JSON contract, config, or artifact.
- `sas_code_selection_policy_v1.json`: JSON contract, config, or artifact.
- `sas_code_suitepack_dev_v1.json`: JSON contract, config, or artifact.
- `sas_code_suitepack_heldout_v1.json`: JSON contract, config, or artifact.
- `sas_code_toolchain_manifest_lean4_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 9 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_code_v12_0
find campaigns/rsi_sas_code_v12_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_code_v12_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
