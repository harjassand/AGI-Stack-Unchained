# fixtures

> Path: `campaigns/rsi_model_genesis_v10_0/fixtures`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `math_eval_fixture.json`: JSON contract, config, or artifact.
- `safety_eval_fixture.json`: JSON contract, config, or artifact.
- `science_eval_fixture.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la campaigns/rsi_model_genesis_v10_0/fixtures
find campaigns/rsi_model_genesis_v10_0/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_model_genesis_v10_0/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
