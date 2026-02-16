#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERIFIER_DIR="$ROOT_DIR/kernel/verifier"
META_DIR="$ROOT_DIR/meta_constitution/v1"
BIN="$VERIFIER_DIR/target/release/verifier"

cd "$VERIFIER_DIR"

TOOLCHAIN="$(grep '^rust_toolchain=' toolchain.lock | cut -d= -f2)"
export RUSTUP_TOOLCHAIN="$TOOLCHAIN"

cargo build --release

"$BIN" verify \
  --bundle-dir "$VERIFIER_DIR/tests/fixtures/valid_bundle" \
  --parent-bundle-dir "$VERIFIER_DIR/tests/fixtures/parent_bundle" \
  --meta-dir "$META_DIR" \
  --out "$VERIFIER_DIR/tests/fixtures/valid_receipt.tmp"

"$BIN" verify \
  --bundle-dir "$VERIFIER_DIR/tests/fixtures/invalid_bundle_tamper" \
  --parent-bundle-dir "$VERIFIER_DIR/tests/fixtures/parent_bundle" \
  --meta-dir "$META_DIR" \
  --out "$VERIFIER_DIR/tests/fixtures/invalid_receipt.tmp" || true

"$BIN" verify \
  --bundle-dir "$VERIFIER_DIR/tests/fixtures/invalid_bundle_schema" \
  --parent-bundle-dir "$VERIFIER_DIR/tests/fixtures/parent_bundle" \
  --meta-dir "$META_DIR" \
  --out "$VERIFIER_DIR/tests/fixtures/invalid_schema_receipt.tmp" || true

echo "smoke test completed"
