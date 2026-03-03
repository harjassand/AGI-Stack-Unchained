# ci

> Path: `baremetal_lgp/scripts/ci`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `lint.sh`: shell automation script.
- `test_bench_smoke.sh`: shell automation script.
- `test_faults.sh`: shell automation script.
- `test_integration.sh`: shell automation script.
- `test_property.sh`: shell automation script.
- `test_release_qual.sh`: shell automation script.
- `test_unit.sh`: shell automation script.
- `verify_release_artifacts.sh`: shell automation script.

## File-Type Surface

- `sh`: 8 files

## Operational Checks

```bash
ls -la baremetal_lgp/scripts/ci
find baremetal_lgp/scripts/ci -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/scripts/ci | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
