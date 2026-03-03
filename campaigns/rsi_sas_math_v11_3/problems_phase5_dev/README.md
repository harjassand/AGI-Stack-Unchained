# problems_phase5_dev

> Path: `campaigns/rsi_sas_math_v11_3/problems_phase5_dev`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `7c6f601e4ba51437f51b5ce8a1af7809b5019233c2a833cc677967aad611baa4.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `92a7215d1b1889ce43ffc11fd3df23fadd83009cd25d9d7a91fc783b7a0723b7.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `958559b82b5a4d9d81d042f68a4bf65473cc7f79a4b8df79c9d908b281822466.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `b5c47e8802cfddf311ad679fc6ddef047376d32a2857c0bc85300d51ef0ca5b5.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `cf803b358d32a968e1413e2c7a91816376b6ce29d990f567250bee2d476f9b33.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `e349b6a278f56f2376016dd37bd9e091ecab80203c03003b09d89af163bc4a60.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `sha256_7c6f601e4ba51437f51b5ce8a1af7809b5019233c2a833cc677967aad611baa4.statement.txt`: text output or trace artifact.
- `sha256_92a7215d1b1889ce43ffc11fd3df23fadd83009cd25d9d7a91fc783b7a0723b7.statement.txt`: text output or trace artifact.
- `sha256_958559b82b5a4d9d81d042f68a4bf65473cc7f79a4b8df79c9d908b281822466.statement.txt`: text output or trace artifact.
- `sha256_b5c47e8802cfddf311ad679fc6ddef047376d32a2857c0bc85300d51ef0ca5b5.statement.txt`: text output or trace artifact.
- `sha256_cf803b358d32a968e1413e2c7a91816376b6ce29d990f567250bee2d476f9b33.statement.txt`: text output or trace artifact.
- `sha256_e349b6a278f56f2376016dd37bd9e091ecab80203c03003b09d89af163bc4a60.statement.txt`: text output or trace artifact.

## File-Type Surface

- `txt`: 6 files
- `json`: 6 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_math_v11_3/problems_phase5_dev
find campaigns/rsi_sas_math_v11_3/problems_phase5_dev -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_math_v11_3/problems_phase5_dev | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
