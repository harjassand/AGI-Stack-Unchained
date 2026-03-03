# policy_vm_stark_rs_v1

> Path: `CDEL-v2/cdel/v19_0/rust/policy_vm_stark_rs_v1`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `src/`: primary implementation source.

## Key Files

- `Cargo.lock`: dependency lockfile.
- `Cargo.toml`: Rust package manifest.

## File-Type Surface

- `toml`: 1 files
- `lock`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/rust/policy_vm_stark_rs_v1
find CDEL-v2/cdel/v19_0/rust/policy_vm_stark_rs_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/rust/policy_vm_stark_rs_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
