# urc_pages

> Path: `polymath/registry/eudrs_u/memory/urc_pages`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_44b7fb0e233c43b28ba2b2d39a1963d17bfaf313ddd643b18fe3a09fdd69d985.urc_page_v1.bin`: project artifact.

## File-Type Surface

- `bin`: 1 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/memory/urc_pages
find polymath/registry/eudrs_u/memory/urc_pages -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/memory/urc_pages | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
