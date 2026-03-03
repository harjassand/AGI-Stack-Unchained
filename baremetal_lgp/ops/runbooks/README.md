# runbooks

> Path: `baremetal_lgp/ops/runbooks`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `backup_restore.md`: documentation artifact.
- `bootstrap.md`: documentation artifact.
- `challenge_rotation.md`: documentation artifact.
- `daily_ops.md`: documentation artifact.
- `incident_response.md`: documentation artifact.
- `ingress.md`: documentation artifact.
- `install.md`: documentation artifact.
- `recovery.md`: documentation artifact.
- `release.md`: documentation artifact.
- `rollback.md`: documentation artifact.

## File-Type Surface

- `md`: 10 files

## Operational Checks

```bash
ls -la baremetal_lgp/ops/runbooks
find baremetal_lgp/ops/runbooks -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/ops/runbooks | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
