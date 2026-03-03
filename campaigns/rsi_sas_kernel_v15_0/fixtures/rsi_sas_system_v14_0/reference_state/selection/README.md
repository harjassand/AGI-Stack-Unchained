# selection

> Path: `campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/selection`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_abf6d70177057c2ec1d4b472cdd0a03d6a1afadebe61d9a8001e4d180affad16.sas_system_selection_receipt_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/selection
find campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/selection -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/reference_state/selection | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
