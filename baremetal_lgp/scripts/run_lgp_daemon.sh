#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${RUN_ID:-$(date +"%Y%m%d_%H%M%S")}"
OUT_DIR="${ROOT}/runs/${RUN_ID}"
CFG="${CFG:-${ROOT}/config/default.toml}"

mkdir -p "${OUT_DIR}"

# Lower priority (macOS-friendly); ignore failures on non-macOS
if command -v taskpolicy >/dev/null 2>&1; then
  taskpolicy -b $$ >/dev/null 2>&1 || true
fi

# Nice if available
renice 10 $$ >/dev/null 2>&1 || true

exec cargo run --release --manifest-path "${ROOT}/Cargo.toml" --bin lgp_hotloop -- \
  --config "${CFG}" \
  --out "${OUT_DIR}"
