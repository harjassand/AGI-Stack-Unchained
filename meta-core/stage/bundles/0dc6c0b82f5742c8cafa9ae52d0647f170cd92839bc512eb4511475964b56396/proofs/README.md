# proofs

> Path: `meta-core/stage/bundles/0dc6c0b82f5742c8cafa9ae52d0647f170cd92839bc512eb4511475964b56396/proofs`

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
ls -la meta-core/stage/bundles/0dc6c0b82f5742c8cafa9ae52d0647f170cd92839bc512eb4511475964b56396/proofs
find meta-core/stage/bundles/0dc6c0b82f5742c8cafa9ae52d0647f170cd92839bc512eb4511475964b56396/proofs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/0dc6c0b82f5742c8cafa9ae52d0647f170cd92839bc512eb4511475964b56396/proofs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
