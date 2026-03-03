# server

> Path: `tools/omega_mission_control/server`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `__tests__/`: component subtree.

## Key Files

- `artifacts_v18.ts`: TypeScript source module.
- `fs_stream_v18.ts`: TypeScript source module.
- `main.ts`: TypeScript source module.
- `mock_generator_v18.ts`: TypeScript source module.
- `run_resolve_v18.ts`: TypeScript source module.
- `run_scan_v18.ts`: TypeScript source module.
- `security.ts`: TypeScript source module.
- `series_dispatch_v18.ts`: TypeScript source module.
- `ws_protocol_v1.ts`: TypeScript source module.

## File-Type Surface

- `ts`: 9 files

## Operational Checks

```bash
ls -la tools/omega_mission_control/server
find tools/omega_mission_control/server -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega_mission_control/server | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
