# receipts

> Path: `polymath/store/receipts`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `.gitkeep`: project artifact.

## File-Type Surface

- `gitkeep`: 1 files

## Operational Checks

```bash
ls -la polymath/store/receipts
find polymath/store/receipts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/store/receipts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
