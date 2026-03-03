# analysis_incident

> Path: `CDEL-v2/analysis_incident`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `backfill_report.csv`: project artifact.
- `backfill_report_addressability.csv`: project artifact.
- `backfill_report_repl.csv`: project artifact.
- `backfill_report_runs_full.csv`: project artifact.
- `dup_scan.csv`: project artifact.
- `overnight_step6.log`: text output or trace artifact.
- `root_cause.md`: documentation artifact.

## File-Type Surface

- `csv`: 5 files
- `md`: 1 files
- `log`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/analysis_incident
find CDEL-v2/analysis_incident -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/analysis_incident | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
