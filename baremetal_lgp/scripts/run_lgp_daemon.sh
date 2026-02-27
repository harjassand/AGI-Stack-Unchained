#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT}/runs/$(date +"%Y%m%d_%H%M%S")"
mkdir -p "${OUT_DIR}"

exec cargo run --release --manifest-path "${ROOT}/Cargo.toml" --bin lgp_hotloop
