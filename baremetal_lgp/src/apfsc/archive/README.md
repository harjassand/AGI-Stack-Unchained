# archive

> Path: `baremetal_lgp/src/apfsc/archive`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `backend_equiv.rs`: Rust source module.
- `bridge_trace.rs`: Rust source module.
- `canary_trace.rs`: Rust source module.
- `challenge_retirement.rs`: Rust source module.
- `error_atlas.rs`: Rust source module.
- `failure_morph.rs`: Rust source module.
- `family_scores.rs`: Rust source module.
- `formal_policy.rs`: Rust source module.
- `genealogy.rs`: Rust source module.
- `hardware_trace.rs`: Rust source module.
- `law_archive.rs`: Rust source module.
- `macro_registry.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `need_tokens.rs`: Rust source module.
- `paradigm_receipts.rs`: Rust source module.
- `portfolio_trace.rs`: Rust source module.
- `qd_archive.rs`: Rust source module.
- `robustness_trace.rs`: Rust source module.
- `searchlaw_trace.rs`: Rust source module.
- `tool_shadow.rs`: Rust source module.
- `transfer_trace.rs`: Rust source module.

## File-Type Surface

- `rs`: 21 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/apfsc/archive
find baremetal_lgp/src/apfsc/archive -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/apfsc/archive | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
