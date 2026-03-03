# analysis

> Path: `campaigns/rsi_boundless_science_v9_0/analysis`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `analysis.py`: Python module or executable script.

## File-Type Surface

- `py`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_boundless_science_v9_0/analysis
find campaigns/rsi_boundless_science_v9_0/analysis -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_boundless_science_v9_0/analysis | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
