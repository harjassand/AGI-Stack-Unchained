# artifacts

> Path: `campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/artifacts`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_23557dd8a7c86e092d5905cf7572eb2aa1bdb8d459bc3470460ce4618e558922.sas_system_immutable_tree_snapshot_v1.json`: JSON contract, config, or artifact.
- `sha256_49b39968d4a178c82a01b884f4e1f8be235701736f0b6fd156bd89a48d7f4f10.sas_system_perf_report_v1.json`: JSON contract, config, or artifact.
- `sha256_bcb4f5aed10fe99d8151aaf9d57d45d56a42fefb749d01e8309d3a6c49727e8b.sas_system_equivalence_report_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/artifacts
find campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/artifacts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/artifacts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
