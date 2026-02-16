#!/bin/sh
set -eu

ROOT="${1:-.}"
OUT_DIR="${2:-out/capacity_exhaustion}"
BUDGET="${3:-500}"
TASKS="${4:-tasks/stream_1000.jsonl}"

cd "$ROOT"

cdel run-experiment --tasks "$TASKS" --generator enum --out "$OUT_DIR" --seed 0 --budget "$BUDGET"
cdel audit-ledger --fast --root "$OUT_DIR"
