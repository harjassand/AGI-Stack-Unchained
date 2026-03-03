# bin

> Path: `baremetal_lgp/src/bin`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `apf3_judge_daemon.rs`: Rust source module.
- `apf3_omega_architect.rs`: Rust source module.
- `apf3_wake_hotloop.rs`: Rust source module.
- `apfsc_backend_equiv.rs`: Rust source module.
- `apfsc_backup.rs`: Rust source module.
- `apfsc_bridge_eval.rs`: Rust source module.
- `apfsc_build_constellation.rs`: Rust source module.
- `apfsc_build_lowered_candidate.rs`: Rust source module.
- `apfsc_compact.rs`: Rust source module.
- `apfsc_diag_dump.rs`: Rust source module.
- `apfsc_epoch_run.rs`: Rust source module.
- `apfsc_gc.rs`: Rust source module.
- `apfsc_ingest_external.rs`: Rust source module.
- `apfsc_ingest_formal.rs`: Rust source module.
- `apfsc_ingest_prior.rs`: Rust source module.
- `apfsc_ingest_reality.rs`: Rust source module.
- `apfsc_ingest_substrate.rs`: Rust source module.
- `apfsc_ingest_tool.rs`: Rust source module.
- `apfsc_judge_daemon.rs`: Rust source module.
- `apfsc_macro_mine.rs`: Rust source module.
- `apfsc_migrate.rs`: Rust source module.
- `apfsc_portfolio_step.rs`: Rust source module.
- `apfsc_preflight.rs`: Rust source module.
- `apfsc_public_eval.rs`: Rust source module.
- `apfsc_qualify.rs`: Rust source module.
- ... and 17 more files.

## File-Type Surface

- `rs`: 42 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/bin
find baremetal_lgp/src/bin -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/bin | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
