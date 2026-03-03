# f70b1d5399b3711a91c0eebcc081b5289d508a6e2aa65577826858ea0ba6fb96

> Path: `meta-core/store/bundles/f70b1d5399b3711a91c0eebcc081b5289d508a6e2aa65577826858ea0ba6fb96`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `omega/`: component subtree.
- `proofs/`: proof material and verification evidence.
- `ruleset/`: component subtree.

## Key Files

- `constitution.manifest.json`: JSON contract, config, or artifact.
- `kernel_receipt.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la meta-core/store/bundles/f70b1d5399b3711a91c0eebcc081b5289d508a6e2aa65577826858ea0ba6fb96
find meta-core/store/bundles/f70b1d5399b3711a91c0eebcc081b5289d508a6e2aa65577826858ea0ba6fb96 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/store/bundles/f70b1d5399b3711a91c0eebcc081b5289d508a6e2aa65577826858ea0ba6fb96 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
