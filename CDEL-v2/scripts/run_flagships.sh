#!/bin/sh
set -eu

ROOT="${ROOT:-.}"
RUNS_BASE="${RUNS_BASE:-runs/flagships}"
ANALYSIS_BASE="${ANALYSIS_BASE:-analysis/flagships}"
OVERWRITE="${OVERWRITE:-0}"

SUITES="${1:-addressability capacity certificates}"

for suite in $SUITES; do
  MATRIX="experiments/flagships/${suite}.json"
  RUN_DIR="${RUNS_BASE}/${suite}"
  ANALYSIS_DIR="${ANALYSIS_BASE}/${suite}"

  if [ -d "$RUN_DIR" ] && [ "$(ls -A "$RUN_DIR")" ]; then
    if [ "$OVERWRITE" = "1" ]; then
      rm -rf "$RUN_DIR"
    else
      echo "Run directory exists: $RUN_DIR"
      exit 1
    fi
  fi

  if [ -d "$ANALYSIS_DIR" ] && [ "$(ls -A "$ANALYSIS_DIR")" ]; then
    if [ "$OVERWRITE" = "1" ]; then
      rm -rf "$ANALYSIS_DIR"
    else
      echo "Analysis directory exists: $ANALYSIS_DIR"
      exit 1
    fi
  fi

  mkdir -p "$RUN_DIR"
  mkdir -p "$ANALYSIS_DIR"

  python3 experiments/run_matrix.py --matrix "$MATRIX" --out "$RUN_DIR" --overwrite --root "$ROOT"
  for run_dir in "$RUN_DIR"/*; do
    if [ -d "$run_dir" ]; then
      cdel audit-run --root "$run_dir"
    fi
  done

  python3 analysis/aggregate_runs.py --runs "$RUN_DIR" --out "$ANALYSIS_DIR"
  python3 analysis/export_curves.py --master "$ANALYSIS_DIR/master_tasks.csv" --out "$ANALYSIS_DIR/curves"
  python3 analysis/check_claims.py --runs "$RUN_DIR" --out "$ANALYSIS_DIR/claims_report.json" --suite "$suite"
  python3 analysis/make_summary.py --master-runs "$ANALYSIS_DIR/master_runs.csv" --claims "$ANALYSIS_DIR/claims_report.json" --out "$ANALYSIS_DIR/README_summary.md"
done
