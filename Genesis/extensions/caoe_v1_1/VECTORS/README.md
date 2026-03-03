# VECTORS

> Path: `Genesis/extensions/caoe_v1_1/VECTORS`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `canon_vectors_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la Genesis/extensions/caoe_v1_1/VECTORS
find Genesis/extensions/caoe_v1_1/VECTORS -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/extensions/caoe_v1_1/VECTORS | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
