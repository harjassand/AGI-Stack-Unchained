# ingress

> Path: `baremetal_lgp/src/apfsc/ingress`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `formal.rs`: Rust source module.
- `judge.rs`: Rust source module.
- `manifest.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `prior.rs`: Rust source module.
- `reality.rs`: Rust source module.
- `receipts.rs`: Rust source module.
- `substrate.rs`: Rust source module.
- `tool.rs`: Rust source module.

## File-Type Surface

- `rs`: 9 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/apfsc/ingress
find baremetal_lgp/src/apfsc/ingress -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/apfsc/ingress | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
