# fixtures

> Path: `tools/polymath/fixtures`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `pubchem_weight300_snapshot_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la tools/polymath/fixtures
find tools/polymath/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/polymath/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
