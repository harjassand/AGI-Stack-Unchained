# release

> Path: `baremetal_lgp/scripts/release`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `build_release.sh`: shell automation script.
- `generate_provenance.sh`: shell automation script.
- `generate_sbom.sh`: shell automation script.
- `publish_release.sh`: shell automation script.
- `rollback_release.sh`: shell automation script.
- `sign_release.sh`: shell automation script.

## File-Type Surface

- `sh`: 6 files

## Operational Checks

```bash
ls -la baremetal_lgp/scripts/release
find baremetal_lgp/scripts/release -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/scripts/release | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
