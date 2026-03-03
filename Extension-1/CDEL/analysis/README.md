# analysis

> Path: `Extension-1/CDEL/analysis`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `__init__.py`: Python module or executable script.
- `aggregate_runs.py`: Python module or executable script.
- `capacity_breakdown.py`: Python module or executable script.
- `check_claims.py`: Python module or executable script.
- `compute_reuse_hygiene.py`: Python module or executable script.
- `derive_reuse_hygiene_thresholds.py`: Python module or executable script.
- `env.txt`: text output or trace artifact.
- `export_curves.py`: Python module or executable script.
- `make_summary.py`: Python module or executable script.
- `validate_manifest.py`: Python module or executable script.
- `validate_run_dir.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files
- `txt`: 1 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/analysis
find Extension-1/CDEL/analysis -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/analysis | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
