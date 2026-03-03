# native_jit

> Path: `baremetal_lgp/native_jit`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `jit_trampoline.c`: C/C++ source or header.
- `jit_trampoline.h`: C/C++ source or header.
- `sniper.c`: C/C++ source or header.
- `sniper.h`: C/C++ source or header.

## File-Type Surface

- `h`: 2 files
- `c`: 2 files

## Operational Checks

```bash
ls -la baremetal_lgp/native_jit
find baremetal_lgp/native_jit -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/native_jit | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
