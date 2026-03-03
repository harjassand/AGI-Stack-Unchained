# src

> Path: `CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/src`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `abi.rs`: Rust source module.
- `bench.rs`: Rust source module.
- `cost.rs`: Rust source module.
- `decode.rs`: Rust source module.
- `lift.rs`: Rust source module.
- `main.rs`: Rust source module.
- `mmap_exec.rs`: Rust source module.
- `patch.rs`: Rust source module.
- `trace.rs`: Rust source module.
- `wx_memory.rs`: Rust source module.

## File-Type Surface

- `rs`: 10 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/src
find CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/src -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/src | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
