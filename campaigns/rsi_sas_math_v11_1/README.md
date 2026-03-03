# rsi_sas_math_v11_1

> Path: `campaigns/rsi_sas_math_v11_1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `problems/`: component subtree.
- `problems_phase4_dev/`: component subtree.
- `problems_phase4_heldout/`: component subtree.
- `problems_phase5_dev/`: component subtree.
- `problems_phase5_heldout/`: component subtree.

## Key Files

- `baseline_policy_ir_v1.json`: JSON contract, config, or artifact.
- `boundless_math_pack_dev_v1.json`: JSON contract, config, or artifact.
- `boundless_math_pack_heldout_v1.json`: JSON contract, config, or artifact.
- `math_toolchain_manifest_lean4_v1.json`: JSON contract, config, or artifact.
- `math_toolchain_manifest_toy_kernel_v1.json`: JSON contract, config, or artifact.
- `olympiad_manifest_v1.json`: JSON contract, config, or artifact.
- `rsi_sas_math_pack_v1.json`: JSON contract, config, or artifact.
- `sas_conjecture_gen_config_v1.json`: JSON contract, config, or artifact.
- `sas_conjecture_selection_policy_v1.json`: JSON contract, config, or artifact.
- `sas_math_lease_token_v1.json`: JSON contract, config, or artifact.
- `sas_math_policy_allowlist_v1.json`: JSON contract, config, or artifact.
- `sas_math_search_config_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 12 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_math_v11_1
find campaigns/rsi_sas_math_v11_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_math_v11_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
