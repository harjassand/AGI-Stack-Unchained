# ccai_x_mind_v2

> Path: `Genesis/test_vectors/ccai_x_mind_v2`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `base_registry.json`: JSON contract, config, or artifact.
- `mechanism_registry_diff.json`: JSON contract, config, or artifact.
- `mechanism_registry_diff_invalid.json`: JSON contract, config, or artifact.
- `target_registry.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 4 files

## Operational Checks

```bash
ls -la Genesis/test_vectors/ccai_x_mind_v2
find Genesis/test_vectors/ccai_x_mind_v2 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/test_vectors/ccai_x_mind_v2 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
