# 960d136a6e4ec2a23f794c673c8a53b8fee982bc1a05a51b518569fccfe07020

> Path: `meta-core/stage/bundles/960d136a6e4ec2a23f794c673c8a53b8fee982bc1a05a51b518569fccfe07020`

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
ls -la meta-core/stage/bundles/960d136a6e4ec2a23f794c673c8a53b8fee982bc1a05a51b518569fccfe07020
find meta-core/stage/bundles/960d136a6e4ec2a23f794c673c8a53b8fee982bc1a05a51b518569fccfe07020 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/stage/bundles/960d136a6e4ec2a23f794c673c8a53b8fee982bc1a05a51b518569fccfe07020 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
