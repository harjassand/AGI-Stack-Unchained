# rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1

> Path: `campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `baselines/`: component subtree.
- `goals/`: component subtree.

## Key Files

- `healthcheck_suitepack_v1.json`: JSON contract, config, or artifact.
- `omega_allowlists_v1.json`: JSON contract, config, or artifact.
- `omega_budgets_v1.json`: JSON contract, config, or artifact.
- `omega_capability_registry_v2.json`: JSON contract, config, or artifact.
- `omega_objectives_v1.json`: JSON contract, config, or artifact.
- `omega_policy_ir_v1.json`: JSON contract, config, or artifact.
- `omega_runaway_config_v1.json`: JSON contract, config, or artifact.
- `rsi_omega_daemon_pack_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1
find campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_omega_daemon_v19_0_phase4b_native_transpiler_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
