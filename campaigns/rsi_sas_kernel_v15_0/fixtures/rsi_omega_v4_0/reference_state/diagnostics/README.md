# diagnostics

> Path: `campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_omega_v4_0/reference_state/diagnostics`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `rsi_swarm_receipt_v5.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_omega_v4_0/reference_state/diagnostics
find campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_omega_v4_0/reference_state/diagnostics -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_omega_v4_0/reference_state/diagnostics | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
