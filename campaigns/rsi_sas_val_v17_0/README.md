# rsi_sas_val_v17_0

> Path: `campaigns/rsi_sas_val_v17_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `fixtures/`: deterministic fixture data.
- `microkernels/`: component subtree.
- `patches/`: component subtree.
- `redteam_patches/`: component subtree.
- `toolchains/`: component subtree.
- `workload/`: component subtree.

## Key Files

- `rsi_sas_val_pack_v17_0.json`: JSON contract, config, or artifact.
- `sas_val_policy_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_val_v17_0
find campaigns/rsi_sas_val_v17_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_val_v17_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
