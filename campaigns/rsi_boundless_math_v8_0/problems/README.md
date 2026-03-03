# problems

> Path: `campaigns/rsi_boundless_math_v8_0/problems`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `30bca311c2edf61234a65797c051d4b0d87c2685f540b3cff50e071c202c5b30.math_problem_spec_v1.json`: JSON contract, config, or artifact.
- `sha256_1841c2aa0eb8996bce8be7e189a95dd0520563e6c6fa874a472207efe3a055a9.statement.txt`: text output or trace artifact.

## File-Type Surface

- `txt`: 1 files
- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_boundless_math_v8_0/problems
find campaigns/rsi_boundless_math_v8_0/problems -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_boundless_math_v8_0/problems | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
