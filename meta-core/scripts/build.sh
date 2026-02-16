#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR/meta_constitution/v1"
./build_meta_hash.sh

cd "$ROOT_DIR/kernel/verifier"
./build.sh
