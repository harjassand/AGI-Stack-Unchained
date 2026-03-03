# urc_pt

> Path: `polymath/registry/eudrs_u/memory/urc_pt`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_0a3a631a4263ba26a921d6fb1c414ff47e031a8b3ebf5cc0d0cfe428b32c503f.urc_page_table_node_v1.bin`: project artifact.
- `sha256_0f8df0cbcddb5b8e254b604e987df39554011347bb1e2edd5963fd7837541c2a.urc_page_table_node_v1.bin`: project artifact.
- `sha256_56eae96a9a748bccd1a09be9ea3e025bd85a35e3876db0095712158e86c086fd.urc_page_table_node_v1.bin`: project artifact.
- `sha256_a6e377c8fc8a5ffff40dd2e0a60519a9812b9eba8ad56324b064384c44f501bd.urc_page_table_node_v1.bin`: project artifact.

## File-Type Surface

- `bin`: 4 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/memory/urc_pt
find polymath/registry/eudrs_u/memory/urc_pt -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/memory/urc_pt | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
