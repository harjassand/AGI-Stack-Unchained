# problems_phase5_heldout

> Path: `campaigns/rsi_sas_math_v11_0/problems_phase5_heldout`

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
- `sha256_7c6f601e4ba51437f51b5ce8a1af7809b5019233c2a833cc677967aad611baa4.statement.txt`: text output or trace artifact.

## File-Type Surface

- `txt`: 1 files
- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_math_v11_0/problems_phase5_heldout
find campaigns/rsi_sas_math_v11_0/problems_phase5_heldout -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_math_v11_0/problems_phase5_heldout | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
