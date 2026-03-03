# tools

> Path: `CDEL-v2/tools`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `backfill_audits.py`: Python module or executable script.
- `backfill_metrics.py`: Python module or executable script.
- `build_portfolio_from_generator.py`: Python module or executable script.
- `proposer_capability_dryrun_v1_5r.py`: Python module or executable script.
- `repro_cache_case.json`: JSON contract, config, or artifact.
- `repro_cache_diff.py`: Python module or executable script.
- `verify_sealing_r5_2.sh`: shell automation script.

## File-Type Surface

- `py`: 5 files
- `sh`: 1 files
- `json`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/tools
find CDEL-v2/tools -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/tools | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
