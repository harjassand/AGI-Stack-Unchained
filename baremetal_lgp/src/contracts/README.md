# contracts

> Path: `baremetal_lgp/src/contracts`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `abi.rs`: Rust source module.
- `constants.rs`: Rust source module.
- `data.rs`: Rust source module.
- `fuel.rs`: Rust source module.
- `isa.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `traits.rs`: Rust source module.

## File-Type Surface

- `rs`: 7 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/contracts
find baremetal_lgp/src/contracts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/contracts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
