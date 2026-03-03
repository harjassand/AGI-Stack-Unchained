# omega

> Path: `meta-core/store/bundles/6628bdb3acea6f69c7a6d3c121bc4e9810ab82c19d3347066dc602887b914f5e/omega`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `omega_activation_binding_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la meta-core/store/bundles/6628bdb3acea6f69c7a6d3c121bc4e9810ab82c19d3347066dc602887b914f5e/omega
find meta-core/store/bundles/6628bdb3acea6f69c7a6d3c121bc4e9810ab82c19d3347066dc602887b914f5e/omega -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/store/bundles/6628bdb3acea6f69c7a6d3c121bc4e9810ab82c19d3347066dc602887b914f5e/omega | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
