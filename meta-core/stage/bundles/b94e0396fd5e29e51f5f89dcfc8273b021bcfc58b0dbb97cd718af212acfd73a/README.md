# b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a

> Path: `meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a`

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
ls -la meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a
find meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/b94e0396fd5e29e51f5f89dcfc8273b021bcfc58b0dbb97cd718af212acfd73a | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
