#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CDEL_ROOT:-}" ]]; then
  echo "CDEL_ROOT is required" >&2
  exit 2
fi

CONFIG=${CONFIG:-"genesis/configs/default.json"}
LEDGER_DIR=${LEDGER_DIR:-"genesis/.cdel_ledger_e2e_v0_3"}
RECEIPTS_DIR=${RECEIPTS_DIR:-"genesis/receipts"}
RUN_LOG=${RUN_LOG:-"genesis_run.jsonl"}
ARCHIVE_LOG=${ARCHIVE_LOG:-"genesis_archive.jsonl"}
SUMMARY_LOG=${SUMMARY_LOG:-"genesis_summary.json"}
LIBRARY_PATH=${LIBRARY_PATH:-"genesis/library.json"}
CALIBRATION_PATH=${CALIBRATION_PATH:-"genesis/shadow_calibration.json"}

rm -rf "$LEDGER_DIR"
rm -rf "$RECEIPTS_DIR"
rm -f "$RUN_LOG" "$ARCHIVE_LOG" "$SUMMARY_LOG" "$LIBRARY_PATH" "$CALIBRATION_PATH"
mkdir -p "$LEDGER_DIR"

CDEL_ROOT="$CDEL_ROOT" \
LEDGER_DIR="$LEDGER_DIR" \
python3 genesis/run_end_to_end_v0_3.py --config "$CONFIG"
