# common

> Path: `tools/omega_mission_control/components/common`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `JsonBlock.tsx`: TypeScript source module.
- `OmegaDashboard.tsx`: TypeScript source module.
- `OmegaSeriesDashboard.tsx`: TypeScript source module.

## File-Type Surface

- `tsx`: 3 files

## Operational Checks

```bash
ls -la tools/omega_mission_control/components/common
find tools/omega_mission_control/components/common -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega_mission_control/components/common | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
