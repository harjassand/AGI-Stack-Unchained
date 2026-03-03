# cfg

> Path: `baremetal_lgp/src/cfg`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ir.rs`: Rust source module.
- `linker.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `verify.rs`: Rust source module.

## File-Type Surface

- `rs`: 4 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/cfg
find baremetal_lgp/src/cfg -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/cfg | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
