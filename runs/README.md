# Runs

Workspace for execution outputs produced by orchestrators, campaigns, and verification tasks.

## Purpose

- Collect run-local artifacts without polluting source trees.
- Provide a predictable root for tooling that expects `--out-dir runs/<run_id>`.

## Conventions

1. Use descriptive run IDs (for example: `runs/omega_v19_phase4_probe_2026-03-01`).
2. Keep reproducibility metadata inside each run directory (config snapshot, seed, receipt pointers).
3. Treat run outputs as ephemeral unless explicitly promoted into canonical evidence paths.

## Hygiene

- Safe to prune stale runs when disk pressure is high.
- Do not store hand-edited source-of-truth contracts here.
