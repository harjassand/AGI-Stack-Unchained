# verifier

> Path: `meta-core/kernel/verifier`

## Mission

Promotion, staging, verification, and rollback control-plane foundations.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `src/`: primary implementation source.
- `tests/`: tests and validation assets.

## Key Files

- `Cargo.lock`: dependency lockfile.
- `Cargo.toml`: Rust package manifest.
- `KERNEL_HASH`: project artifact.
- `build.sh`: shell automation script.
- `toolchain.lock`: dependency lockfile.

## File-Type Surface

- `lock`: 2 files
- `toml`: 1 files
- `sh`: 1 files
- `(no_ext)`: 1 files

## Operational Checks

```bash
ls -la meta-core/kernel/verifier
find meta-core/kernel/verifier -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files meta-core/kernel/verifier | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
