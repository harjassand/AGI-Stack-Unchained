# meta_constitution

> Path: `meta-core/meta_constitution`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `v1/`: component subtree.
- `v10_0/`: component subtree.
- `v11_0/`: component subtree.
- `v11_1/`: component subtree.
- `v11_2/`: component subtree.
- `v11_3/`: component subtree.
- `v1_5r/`: component subtree.
- `v1_6r/`: component subtree.
- `v1_7r/`: component subtree.
- `v1_8r/`: component subtree.
- `v1_9r/`: component subtree.
- `v2_0/`: component subtree.
- `v2_1/`: component subtree.
- `v2_2/`: component subtree.
- `v2_3/`: component subtree.
- `v3_0/`: component subtree.
- `v3_1/`: component subtree.
- `v3_2/`: component subtree.
- `v3_3/`: component subtree.
- `v4_0/`: component subtree.
- ... and 5 more child directories.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la meta-core/meta_constitution
find meta-core/meta_constitution -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/meta_constitution | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
