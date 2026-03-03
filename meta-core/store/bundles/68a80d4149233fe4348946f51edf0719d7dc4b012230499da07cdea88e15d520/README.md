# 68a80d4149233fe4348946f51edf0719d7dc4b012230499da07cdea88e15d520

> Path: `meta-core/store/bundles/68a80d4149233fe4348946f51edf0719d7dc4b012230499da07cdea88e15d520`

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
ls -la meta-core/store/bundles/68a80d4149233fe4348946f51edf0719d7dc4b012230499da07cdea88e15d520
find meta-core/store/bundles/68a80d4149233fe4348946f51edf0719d7dc4b012230499da07cdea88e15d520 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/store/bundles/68a80d4149233fe4348946f51edf0719d7dc4b012230499da07cdea88e15d520 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
