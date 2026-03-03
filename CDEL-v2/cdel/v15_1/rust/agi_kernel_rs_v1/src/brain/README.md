# brain

> Path: `CDEL-v2/cdel/v15_1/rust/agi_kernel_rs_v1/src/brain`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `branch_sig.rs`: Rust source module.
- `budget.rs`: Rust source module.
- `context.rs`: Rust source module.
- `decision.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `policy.rs`: Rust source module.
- `select.rs`: Rust source module.

## File-Type Surface

- `rs`: 7 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_1/rust/agi_kernel_rs_v1/src/brain
find CDEL-v2/cdel/v15_1/rust/agi_kernel_rs_v1/src/brain -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_1/rust/agi_kernel_rs_v1/src/brain | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
