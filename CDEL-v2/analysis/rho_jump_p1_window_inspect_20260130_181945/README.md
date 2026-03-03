# rho_jump_p1_window_inspect_20260130_181945

> Path: `CDEL-v2/analysis/rho_jump_p1_window_inspect_20260130_181945`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `epoch_1_macro_tokenization_report_heldout_v1.json`: JSON contract, config, or artifact.
- `epoch_1_rho_report_v1.json`: JSON contract, config, or artifact.
- `epoch_1_rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `epoch_2_macro_tokenization_report_heldout_v1.json`: JSON contract, config, or artifact.
- `epoch_2_rho_report_v1.json`: JSON contract, config, or artifact.
- `epoch_2_rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `epoch_3_macro_tokenization_report_heldout_v1.json`: JSON contract, config, or artifact.
- `epoch_3_rho_report_v1.json`: JSON contract, config, or artifact.
- `epoch_3_rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `epoch_4_macro_tokenization_report_heldout_v1.json`: JSON contract, config, or artifact.
- `epoch_4_rho_report_v1.json`: JSON contract, config, or artifact.
- `epoch_4_rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `epoch_5_macro_tokenization_report_heldout_v1.json`: JSON contract, config, or artifact.
- `epoch_5_rho_report_v1.json`: JSON contract, config, or artifact.
- `epoch_5_rsi_ignition_report_v1.json`: JSON contract, config, or artifact.
- `index.txt`: text output or trace artifact.

## File-Type Surface

- `json`: 15 files
- `txt`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/analysis/rho_jump_p1_window_inspect_20260130_181945
find CDEL-v2/analysis/rho_jump_p1_window_inspect_20260130_181945 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/analysis/rho_jump_p1_window_inspect_20260130_181945 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
