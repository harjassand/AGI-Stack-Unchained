# rsi_omega_daemon_v19_0_phase4d_epistemic_airlock

> Path: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `baselines/`: component subtree.
- `entries/`: component subtree.
- `goals/`: component subtree.

## Key Files

- `cert_invariance_contract_v1.json`: JSON contract, config, or artifact.
- `coordinator_isa_program_v1.json`: JSON contract, config, or artifact.
- `coordinator_opcode_table_v1.json`: JSON contract, config, or artifact.
- `corpus_descriptor_v1.json`: JSON contract, config, or artifact.
- `graph_invariance_contract_v1.json`: JSON contract, config, or artifact.
- `healthcheck_suitepack_v1.json`: JSON contract, config, or artifact.
- `j_comparison_v1.json`: JSON contract, config, or artifact.
- `omega_allowlists_v1.json`: JSON contract, config, or artifact.
- `omega_budgets_v1.json`: JSON contract, config, or artifact.
- `omega_capability_registry_v2.json`: JSON contract, config, or artifact.
- `omega_objectives_v1.json`: JSON contract, config, or artifact.
- `omega_policy_ir_v1.json`: JSON contract, config, or artifact.
- `omega_runaway_config_v1.json`: JSON contract, config, or artifact.
- `rsi_epistemic_reduce_pack_v1.json`: JSON contract, config, or artifact.
- `rsi_omega_daemon_pack_v1.json`: JSON contract, config, or artifact.
- `shadow_evaluation_tiers_v1.json`: JSON contract, config, or artifact.
- `shadow_protected_roots_profile_v1.json`: JSON contract, config, or artifact.
- `shadow_regime_proposal_v1.json`: JSON contract, config, or artifact.
- `type_binding_invariance_contract_v1.json`: JSON contract, config, or artifact.
- `witnessed_determinism_profile_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 20 files

## Operational Checks

```bash
ls -la campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock
find campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
