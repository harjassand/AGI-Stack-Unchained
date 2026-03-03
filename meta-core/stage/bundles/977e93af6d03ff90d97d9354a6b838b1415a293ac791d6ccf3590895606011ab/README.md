# 977e93af6d03ff90d97d9354a6b838b1415a293ac791d6ccf3590895606011ab

> Path: `meta-core/stage/bundles/977e93af6d03ff90d97d9354a6b838b1415a293ac791d6ccf3590895606011ab`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `proofs/`: proof material and verification evidence.
- `ruleset/`: component subtree.

## Key Files

- `constitution.manifest.json`: JSON contract, config, or artifact.
- `kernel_receipt.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la meta-core/stage/bundles/977e93af6d03ff90d97d9354a6b838b1415a293ac791d6ccf3590895606011ab
find meta-core/stage/bundles/977e93af6d03ff90d97d9354a6b838b1415a293ac791d6ccf3590895606011ab -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/977e93af6d03ff90d97d9354a6b838b1415a293ac791d6ccf3590895606011ab | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
