# macros

> Path: `campaigns/rsi_real_ignite_v1/macros`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ad7996686bd728871629c3b3c835cf5a8d6d3be4746f297d051482946c29079c.json`: JSON contract, config, or artifact.
- `c92c00025b2c9c33d217e077d1490839513fc325994f699521ba6da7e62ebc2f.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_ignite_v1/macros
find campaigns/rsi_real_ignite_v1/macros -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_ignite_v1/macros | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
