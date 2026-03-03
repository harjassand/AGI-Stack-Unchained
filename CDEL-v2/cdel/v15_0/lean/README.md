# lean

> Path: `CDEL-v2/cdel/v15_0/lean`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `KernelSafetyV15.lean`: project artifact.
- `SASKernelPreambleV15.lean`: project artifact.

## File-Type Surface

- `lean`: 2 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v15_0/lean
find CDEL-v2/cdel/v15_0/lean -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v15_0/lean | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
