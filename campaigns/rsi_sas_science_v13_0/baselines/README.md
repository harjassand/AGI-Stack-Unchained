# baselines

> Path: `campaigns/rsi_sas_science_v13_0/baselines`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `baseline_constant_velocity_v1.sas_science_theory_ir_v1.json`: JSON contract, config, or artifact.
- `baseline_hooke_central_v1.sas_science_theory_ir_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_science_v13_0/baselines
find campaigns/rsi_sas_science_v13_0/baselines -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_science_v13_0/baselines | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
