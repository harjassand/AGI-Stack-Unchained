# rsi_sas_kernel_v15_0

> Path: `campaigns/rsi_sas_kernel_v15_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.

## Key Files

- `capability_registry_v2.json`: JSON contract, config, or artifact.
- `fixture_matrix_v1.json`: JSON contract, config, or artifact.
- `rsi_sas_kernel_pack_v1.json`: JSON contract, config, or artifact.
- `sas_kernel_policy_v1.json`: JSON contract, config, or artifact.
- `suitepack_dev_v1.json`: JSON contract, config, or artifact.
- `suitepack_heldout_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_kernel_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_lean_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_py_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_rust_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 10 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_0
find campaigns/rsi_sas_kernel_v15_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
