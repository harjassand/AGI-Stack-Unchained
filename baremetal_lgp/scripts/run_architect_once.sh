#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec cargo run --release --manifest-path "${ROOT}/Cargo.toml" --bin architect
