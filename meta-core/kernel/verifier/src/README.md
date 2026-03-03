# src

> Path: `meta-core/kernel/verifier/src`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ir/`: component subtree.

## Key Files

- `base64.rs`: Rust source module.
- `canonical_json.rs`: Rust source module.
- `hash.rs`: Rust source module.
- `immutable_core.rs`: Rust source module.
- `lib.rs`: Rust source module.
- `main.rs`: Rust source module.
- `promotion.rs`: Rust source module.
- `schema_checks.rs`: Rust source module.
- `verify.rs`: Rust source module.

## File-Type Surface

- `rs`: 9 files

## Operational Checks

```bash
ls -la meta-core/kernel/verifier/src
find meta-core/kernel/verifier/src -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/kernel/verifier/src | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
