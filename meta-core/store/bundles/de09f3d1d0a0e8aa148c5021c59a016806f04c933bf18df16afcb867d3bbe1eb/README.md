# de09f3d1d0a0e8aa148c5021c59a016806f04c933bf18df16afcb867d3bbe1eb

> Path: `meta-core/store/bundles/de09f3d1d0a0e8aa148c5021c59a016806f04c933bf18df16afcb867d3bbe1eb`

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
ls -la meta-core/store/bundles/de09f3d1d0a0e8aa148c5021c59a016806f04c933bf18df16afcb867d3bbe1eb
find meta-core/store/bundles/de09f3d1d0a0e8aa148c5021c59a016806f04c933bf18df16afcb867d3bbe1eb -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/store/bundles/de09f3d1d0a0e8aa148c5021c59a016806f04c933bf18df16afcb867d3bbe1eb | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
