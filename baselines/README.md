# Baselines

This directory holds canonical baseline artifacts used for regression and challenge comparisons.

## Scope

- Store immutable baseline reports that define reference performance.
- Keep reports machine-readable so CI and verifier paths can consume them directly.
- Separate baseline outputs from active run outputs in `/runs`.

## Structure

- `pi0_grand_challenge_v1/`: Baseline for the PI0 grand challenge heldout suite.

## Contracts

- Baseline reports are expected to follow `baseline_report_v1`.
- IDs, suite names, and hash fields are treated as immutable evidence once published.
- New baselines should be added as new folders instead of editing historical files in place.

## Authoring Checklist

1. Emit the report with explicit `schema` and `spec_version`.
2. Include solved-task hash/material even when solved set is empty.
3. Name the folder by baseline ID to keep references stable.
