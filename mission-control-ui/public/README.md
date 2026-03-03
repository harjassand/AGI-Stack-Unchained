# public

> Path: `mission-control-ui/public`

## Mission

Frontend operator interface for telemetry, mission ingest, and live control visibility.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `file.svg`: project artifact.
- `globe.svg`: project artifact.
- `next.svg`: project artifact.
- `vercel.svg`: project artifact.
- `window.svg`: project artifact.

## File-Type Surface

- `svg`: 5 files

## Operational Checks

```bash
ls -la mission-control-ui/public
find mission-control-ui/public -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files mission-control-ui/public | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
