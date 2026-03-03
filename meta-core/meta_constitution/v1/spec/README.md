# spec

> Path: `meta-core/meta_constitution/v1/spec`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `activation_protocol_v1.md`: documentation artifact.
- `bundle_hashing_v1.md`: documentation artifact.
- `costvec.json`: JSON contract, config, or artifact.
- `dominance_witness_v1.md`: documentation artifact.
- `ir_limits.json`: JSON contract, config, or artifact.
- `metaconst.json`: JSON contract, config, or artifact.
- `migration_totality_v1.md`: documentation artifact.
- `policy.json`: JSON contract, config, or artifact.
- `statement_set.json`: JSON contract, config, or artifact.
- `toolchain_merkle_root_v1.md`: documentation artifact.

## File-Type Surface

- `md`: 5 files
- `json`: 5 files

## Operational Checks

```bash
ls -la meta-core/meta_constitution/v1/spec
find meta-core/meta_constitution/v1/spec -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/meta_constitution/v1/spec | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
