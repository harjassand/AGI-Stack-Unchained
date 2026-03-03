# prod

> Path: `baremetal_lgp/src/apfsc/prod`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `audit.rs`: Rust source module.
- `auth.rs`: Rust source module.
- `backup.rs`: Rust source module.
- `buildinfo.rs`: Rust source module.
- `compaction.rs`: Rust source module.
- `control_api.rs`: Rust source module.
- `control_db.rs`: Rust source module.
- `daemon.rs`: Rust source module.
- `diagnostics.rs`: Rust source module.
- `gc.rs`: Rust source module.
- `health.rs`: Rust source module.
- `install.rs`: Rust source module.
- `jobs.rs`: Rust source module.
- `journal.rs`: Rust source module.
- `lease.rs`: Rust source module.
- `leases.rs`: Rust source module.
- `migration.rs`: Rust source module.
- `mod.rs`: Rust source module.
- `preflight.rs`: Rust source module.
- `profiles.rs`: Rust source module.
- `recovery.rs`: Rust source module.
- `release_manifest.rs`: Rust source module.
- `restore.rs`: Rust source module.
- `retention.rs`: Rust source module.
- `secrets.rs`: Rust source module.
- ... and 3 more files.

## File-Type Surface

- `rs`: 28 files

## Operational Checks

```bash
ls -la baremetal_lgp/src/apfsc/prod
find baremetal_lgp/src/apfsc/prod -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/src/apfsc/prod | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
