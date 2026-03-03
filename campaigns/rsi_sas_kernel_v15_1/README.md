# rsi_sas_kernel_v15_1

> Path: `campaigns/rsi_sas_kernel_v15_1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `brain_corpus/`: component subtree.

## Key Files

- `brain_corpus_suitepack_dev_v1.json`: JSON contract, config, or artifact.
- `brain_corpus_suitepack_heldout_v1.json`: JSON contract, config, or artifact.
- `capability_registry_v2.json`: JSON contract, config, or artifact.
- `rsi_sas_kernel_pack_v15_1.json`: JSON contract, config, or artifact.
- `sas_kernel_policy_v15_1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_kernel_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_lean_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_py_v1.json`: JSON contract, config, or artifact.
- `toolchain_manifest_rust_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 9 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_1
find campaigns/rsi_sas_kernel_v15_1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
