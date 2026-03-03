# accel

> Path: `baremetal_lgp/src/accel`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `accelerate.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `thresholds.rs`: Rust source module.

## File-Type Surface

- `rs`: 3 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/accel
find baremetal_lgp/src/accel -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/accel | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
