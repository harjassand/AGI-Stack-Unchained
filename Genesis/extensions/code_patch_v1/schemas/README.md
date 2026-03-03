# schemas

> Path: `Genesis/extensions/code_patch_v1/schemas`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `code_patch_candidate_v1.json`: JSON contract, config, or artifact.
- `code_patch_policy_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/extensions/code_patch_v1/schemas
find Genesis/extensions/code_patch_v1/schemas -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/extensions/code_patch_v1/schemas | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
