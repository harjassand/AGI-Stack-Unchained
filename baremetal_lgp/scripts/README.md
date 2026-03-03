# scripts

> Path: `baremetal_lgp/scripts`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ci/`: component subtree.
- `release/`: component subtree.

## Key Files

- `apfsc_ingest_prior_alien.sh`: shell automation script.
- `run_lgp_daemon.sh`: shell automation script.

## File-Type Surface

- `sh`: 2 files

## Operational Checks

```bash
ls -la baremetal_lgp/scripts
find baremetal_lgp/scripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/scripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
