#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${APFSC_ROOT:-$HOME/.apfsc}"
CONFIG_PATH="${1:-$REPO_ROOT/fixtures/apfsc/phase4/config/phase4.toml}"
PACK_DIR="$REPO_ROOT/fixtures/apfsc/phase4/prior_alien"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "config not found: $CONFIG_PATH" >&2
  exit 1
fi

if [[ ! -f "$PACK_DIR/manifest.json" ]]; then
  echo "prior_alien manifest missing: $PACK_DIR/manifest.json" >&2
  exit 1
fi

echo "[apfsc] ingesting prior_alien pack into root=$ROOT_DIR"
(
  cd "$REPO_ROOT"
  cargo run --release --bin apfsc_ingest_prior -- \
    --root "$ROOT_DIR" \
    --config "$CONFIG_PATH" \
    --manifest "$PACK_DIR/manifest.json"
)

echo "[apfsc] prior_alien ingested; active snapshot was refreshed"

if [[ "${APFSC_REBUILD_CONSTELLATION:-1}" == "1" ]]; then
  echo "[apfsc] rebuilding active constellation"
  (
    cd "$REPO_ROOT"
    cargo run --release --bin apfsc_build_constellation -- \
      --root "$ROOT_DIR" \
      --config "$CONFIG_PATH"
  )
fi
