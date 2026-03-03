# ir

> Path: `meta-core/kernel/verifier/src/ir`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ast.rs`: Rust source module.
- `eval.rs`: Rust source module.
- `gas.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `static_checks.rs`: Rust source module.

## File-Type Surface

- `rs`: 5 files

## Operational Checks

```bash
ls -la meta-core/kernel/verifier/src/ir
find meta-core/kernel/verifier/src/ir -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/kernel/verifier/src/ir | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
