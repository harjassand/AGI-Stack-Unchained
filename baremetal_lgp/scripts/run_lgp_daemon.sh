#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNS="$ROOT/runs"
mkdir -p "$RUNS"

exec nice -n 10 \
  cargo run --release --manifest-path "${ROOT}/Cargo.toml" --bin lgp_hotloop -- \
    --workers "${LGP_WORKERS:-6}" \
    --fuel-max "${LGP_FUEL_MAX:-200000}" \
    --run-dir "$RUNS/$(date +%Y%m%d_%H%M%S)" \
    --topk-trace "${LGP_TOPK_TRACE:-16}"
