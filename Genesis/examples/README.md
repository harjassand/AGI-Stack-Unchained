# examples

> Path: `Genesis/examples`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `algorithm.capsule.json`: JSON contract, config, or artifact.
- `causal_model.capsule.json`: JSON contract, config, or artifact.
- `experiment.capsule.json`: JSON contract, config, or artifact.
- `mock_pass.capsule.json`: JSON contract, config, or artifact.
- `policy.capsule.json`: JSON contract, config, or artifact.
- `world_model.capsule.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 6 files

## Operational Checks

```bash
ls -la Genesis/examples
find Genesis/examples -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/examples | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
