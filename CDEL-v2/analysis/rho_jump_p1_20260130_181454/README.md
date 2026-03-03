# rho_jump_p1_20260130_181454

> Path: `CDEL-v2/analysis/rho_jump_p1_20260130_181454`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `active_set_diff_e1_e2.patch`: project artifact.
- `ledger_markers.txt`: text output or trace artifact.
- `macro_active_set_current.json`: JSON contract, config, or artifact.
- `macro_ledger_tail.txt`: text output or trace artifact.
- `macro_ledger_v1.jsonl`: project artifact.
- `rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `rsi_reports_all_epochs.txt`: text output or trace artifact.

## File-Type Surface

- `txt`: 3 files
- `json`: 2 files
- `patch`: 1 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/analysis/rho_jump_p1_20260130_181454
find CDEL-v2/analysis/rho_jump_p1_20260130_181454 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/analysis/rho_jump_p1_20260130_181454 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
