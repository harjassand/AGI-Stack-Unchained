#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

TOOLCHAIN="$(grep '^rust_toolchain=' toolchain.lock | cut -d= -f2)"
export RUSTUP_TOOLCHAIN="$TOOLCHAIN"

cargo build --release
shasum -a 256 target/release/verifier | awk '{print $1}' > KERNEL_HASH

cargo test

../../scripts/smoke_test.sh
