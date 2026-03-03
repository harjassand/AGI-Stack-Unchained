# Daemon Runtime State

This directory stores mutable runtime state and artifact caches produced by daemonized orchestration flows.

## Scope

- Persist active policy/model pointers used by runtime loops.
- Store hash-addressed manifests and bundles used for reproducible replay.
- Hold campaign- and subsystem-specific state that is not source code.

## Directory Map

- `oracle_ladder/`: Oracle operator bank snapshots plus active bank pointer.
- `orch_active_inference_v1/`: Active inference query inputs by tick.
- `orch_bandit/`: Bandit policy/runtime state placeholder.
- `orch_policy/`: World-model policy tables, transition datasets, and policy bundles.
- `orch_rl/`: RL dataset manifest staging.
- `proposer_models/`: Proposer model pointers, datasets, and model bundle manifests.
- `rsi_sas_kernel_v15_0/`: Legacy v15.0 kernel daemon config root.
- `rsi_sas_kernel_v15_1/`: v15.1 kernel corpus/suitepack config.
- `rsi_sas_metasearch_v16_0/`: Metasearch runtime pack and toolchain manifests.

## Operational Expectations

1. Hash-addressed files are immutable evidence. Add new files instead of editing historical ones.
2. Active pointers (for example under `active/`) may move as promotion decisions change.
3. Keep schema/version tags intact; these artifacts are consumed by verifiers and replay tooling.
4. Avoid manual edits in this tree unless the change is part of a controlled migration.

## Common Inspection Commands

```bash
ls daemon
ls daemon/oracle_ladder | head
cat daemon/orch_policy/orch_policy_bundle_v1.json
```
