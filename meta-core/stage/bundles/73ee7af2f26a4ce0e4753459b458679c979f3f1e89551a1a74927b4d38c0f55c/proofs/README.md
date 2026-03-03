# proofs

> Path: `meta-core/stage/bundles/73ee7af2f26a4ce0e4753459b458679c979f3f1e89551a1a74927b4d38c0f55c/proofs`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `dominance_witness.json`: JSON contract, config, or artifact.
- `proof_bundle.manifest.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la meta-core/stage/bundles/73ee7af2f26a4ce0e4753459b458679c979f3f1e89551a1a74927b4d38c0f55c/proofs
find meta-core/stage/bundles/73ee7af2f26a4ce0e4753459b458679c979f3f1e89551a1a74927b4d38c0f55c/proofs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/73ee7af2f26a4ce0e4753459b458679c979f3f1e89551a1a74927b4d38c0f55c/proofs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
