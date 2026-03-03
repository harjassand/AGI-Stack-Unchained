# apf3

> Path: `baremetal_lgp/src/apf3`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `a64_scan.rs`: Rust source module.
- `aal_exec.rs`: Rust source module.
- `aal_ir.rs`: Rust source module.
- `digest.rs`: Rust source module.
- `judge.rs`: Rust source module.
- `metachunkpack.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `morphisms.rs`: Rust source module.
- `nativeblock.rs`: Rust source module.
- `omega.rs`: Rust source module.
- `profiler.rs`: Rust source module.
- `sfi.rs`: Rust source module.
- `wake.rs`: Rust source module.

## File-Type Surface

- `rs`: 13 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/apf3
find baremetal_lgp/src/apf3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/apf3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
