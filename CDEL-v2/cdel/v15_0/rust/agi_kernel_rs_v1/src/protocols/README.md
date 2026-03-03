# protocols

> Path: `CDEL-v2/cdel/v15_0/rust/agi_kernel_rs_v1/src/protocols`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `mod.rs`: Rust source module.
- `omega_v4.rs`: Rust source module.
- `sas_system_v14.rs`: Rust source module.

## File-Type Surface

- `rs`: 3 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_0/rust/agi_kernel_rs_v1/src/protocols
find CDEL-v2/cdel/v15_0/rust/agi_kernel_rs_v1/src/protocols -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_0/rust/agi_kernel_rs_v1/src/protocols | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
