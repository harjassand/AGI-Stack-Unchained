# vendor

> Path: `CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/vendor`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `autocfg/`: component subtree.
- `bitflags/`: component subtree.
- `cfg-if/`: component subtree.
- `heck/`: component subtree.
- `indoc/`: component subtree.
- `itoa/`: component subtree.
- `libc/`: component subtree.
- `lock_api/`: component subtree.
- `memchr/`: component subtree.
- `memoffset/`: component subtree.
- `once_cell/`: component subtree.
- `parking_lot/`: component subtree.
- `parking_lot_core/`: component subtree.
- `portable-atomic/`: component subtree.
- `proc-macro2/`: component subtree.
- `pyo3/`: component subtree.
- `pyo3-build-config/`: component subtree.
- `pyo3-ffi/`: component subtree.
- `pyo3-macros/`: component subtree.
- `pyo3-macros-backend/`: component subtree.
- ... and 15 more child directories.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/vendor
find CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/vendor -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v14_0/rust/cdel_workmeter_rs_v1/vendor | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
