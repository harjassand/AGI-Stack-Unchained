# src

> Path: `CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/src`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `bin/`: component subtree.

## Key Files

- `lib.rs`: Rust source module.

## File-Type Surface

- `rs`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/src
find CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/src -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/src | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
