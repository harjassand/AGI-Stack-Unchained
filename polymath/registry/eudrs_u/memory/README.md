# memory

> Path: `polymath/registry/eudrs_u/memory`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `urc_pages/`: component subtree.
- `urc_pt/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/memory
find polymath/registry/eudrs_u/memory -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/memory | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
