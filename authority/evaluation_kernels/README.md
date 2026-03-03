# evaluation_kernels

> Path: `authority/evaluation_kernels`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `ek_active_v1.json`: JSON contract, config, or artifact.
- `ek_omega_v18_0_v1.json`: JSON contract, config, or artifact.
- `ek_omega_v18_0_v2.json`: JSON contract, config, or artifact.
- `ek_omega_v19_ceiling_v1.json`: JSON contract, config, or artifact.
- `ek_omega_v19_phase3_v1.json`: JSON contract, config, or artifact.
- `omega_math_science_task_suite_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 6 files

## Operational Checks

```bash
ls -la authority/evaluation_kernels
find authority/evaluation_kernels -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/evaluation_kernels | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
