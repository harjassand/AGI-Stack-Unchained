# tools

> Path: `CDEL-v2/cdel/v1_6r/tools`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `build_portfolio_from_generator.py`: Python module or executable script.
- `proposer_capability_dryrun_v1_5r.py`: Python module or executable script.
- `verify_ignition_r5_2.sh`: shell automation script.
- `verify_rsi_l4_one_shot.py`: Python module or executable script.
- `verify_rsi_l5_one_shot.py`: Python module or executable script.
- `verify_rsi_l6_one_shot.py`: Python module or executable script.

## File-Type Surface

- `py`: 5 files
- `sh`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v1_6r/tools
find CDEL-v2/cdel/v1_6r/tools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v1_6r/tools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
