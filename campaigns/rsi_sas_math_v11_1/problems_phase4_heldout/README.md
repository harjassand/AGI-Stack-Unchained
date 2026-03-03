# problems_phase4_heldout

> Path: `campaigns/rsi_sas_math_v11_1/problems_phase4_heldout`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `784ee93fe257f03de39f0d762bba11d604b9c5680335616d00e9e905f0c2e4bd.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `e349b6a278f56f2376016dd37bd9e091ecab80203c03003b09d89af163bc4a60.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `sha256_784ee93fe257f03de39f0d762bba11d604b9c5680335616d00e9e905f0c2e4bd.statement.txt`: text output or trace artifact.
- `sha256_e349b6a278f56f2376016dd37bd9e091ecab80203c03003b09d89af163bc4a60.statement.txt`: text output or trace artifact.

## File-Type Surface

- `txt`: 2 files
- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_math_v11_1/problems_phase4_heldout
find campaigns/rsi_sas_math_v11_1/problems_phase4_heldout -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_math_v11_1/problems_phase4_heldout | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
