# static

> Path: `tools/mission_control/mission_control/static`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `app.js`: JavaScript source module.
- `index.html`: project artifact.
- `styles.css`: project artifact.

## File-Type Surface

- `js`: 1 files
- `html`: 1 files
- `css`: 1 files

## Operational Checks

```bash
ls -la tools/mission_control/mission_control/static
find tools/mission_control/mission_control/static -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/mission_control/mission_control/static | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
