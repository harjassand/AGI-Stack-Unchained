# vendor

> Path: `CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/vendor`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

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
ls -la CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/vendor
find CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/vendor -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/vendor | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
