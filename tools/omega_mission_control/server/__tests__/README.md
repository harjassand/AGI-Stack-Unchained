# __tests__

> Path: `tools/omega_mission_control/server/__tests__`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `dispatch_id_roundtrip.test.ts`: TypeScript source module.
- `path_traversal.test.ts`: TypeScript source module.
- `series_grouping.test.ts`: TypeScript source module.
- `series_snapshot_resolution.test.ts`: TypeScript source module.
- `test_utils.ts`: TypeScript source module.

## File-Type Surface

- `ts`: 5 files

## Operational Checks

```bash
ls -la tools/omega_mission_control/server/__tests__
find tools/omega_mission_control/server/__tests__ -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega_mission_control/server/__tests__ | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
