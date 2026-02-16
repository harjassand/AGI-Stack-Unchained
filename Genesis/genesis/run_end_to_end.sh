#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CDEL_ROOT:-}" ]]; then
  echo "CDEL_ROOT is required" >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GENESIS_ROOT=${GENESIS_ROOT:-"$SCRIPT_DIR"}

CONFIG=${CONFIG:-"$GENESIS_ROOT/configs/default.json"}
LEDGER_DIR=${LEDGER_DIR:-"$GENESIS_ROOT/.cdel_ledger_e2e_v0_3"}
RECEIPTS_DIR=${RECEIPTS_DIR:-"$GENESIS_ROOT/receipts"}
RUN_LOG=${RUN_LOG:-"$GENESIS_ROOT/genesis_run.jsonl"}
ARCHIVE_LOG=${ARCHIVE_LOG:-"$GENESIS_ROOT/genesis_archive.jsonl"}
SUMMARY_LOG=${SUMMARY_LOG:-"$GENESIS_ROOT/genesis_summary.json"}
LIBRARY_PATH=${LIBRARY_PATH:-"$GENESIS_ROOT/library.json"}
CALIBRATION_PATH=${CALIBRATION_PATH:-"$GENESIS_ROOT/shadow_calibration.json"}

rm -rf "$LEDGER_DIR"
rm -rf "$RECEIPTS_DIR"
rm -f "$RUN_LOG" "$ARCHIVE_LOG" "$SUMMARY_LOG" "$LIBRARY_PATH" "$CALIBRATION_PATH"
mkdir -p "$LEDGER_DIR"

CDEL_ROOT="$CDEL_ROOT" \
LEDGER_DIR="$LEDGER_DIR" \
python3 "$GENESIS_ROOT/run_end_to_end_v0_3.py" --config "$CONFIG"
