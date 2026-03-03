# schema

> Path: `Genesis/schema`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ccai_x_mind_v1/`: component subtree.
- `ccai_x_mind_v2/`: component subtree.
- `ccai_x_v1/`: component subtree.
- `v10_0/`: component subtree.
- `v11_0/`: component subtree.
- `v11_1/`: component subtree.
- `v11_3/`: component subtree.
- `v12_0/`: component subtree.
- `v13_0/`: component subtree.
- `v14_0/`: component subtree.
- `v15_0/`: component subtree.
- `v15_1/`: component subtree.
- `v16_0/`: component subtree.
- `v16_1/`: component subtree.
- `v17_0/`: component subtree.
- `v18_0/`: component subtree.
- `v19_0/`: component subtree.
- `v1_5r/`: component subtree.
- `v1_6r/`: component subtree.
- `v1_7r/`: component subtree.
- ... and 16 more child directories.

## Key Files

- `.DS_Store`: project artifact.
- `capsule.schema.json`: JSON contract, config, or artifact.
- `receipt.schema.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files
- `DS_Store`: 1 files

## Operational Checks

```bash
ls -la Genesis/schema
find Genesis/schema -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
