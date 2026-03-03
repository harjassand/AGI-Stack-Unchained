# app

> Path: `mission-control-ui/app`

## Mission

Frontend operator interface for telemetry, mission ingest, and live control visibility.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `dev/`: component subtree.

## Key Files

- `favicon.ico`: project artifact.
- `globals.css`: project artifact.
- `layout.tsx`: TypeScript source module.
- `page.tsx`: TypeScript source module.

## File-Type Surface

- `tsx`: 2 files
- `ico`: 1 files
- `css`: 1 files

## Operational Checks

```bash
ls -la mission-control-ui/app
find mission-control-ui/app -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files mission-control-ui/app | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
