#!/usr/bin/env bash
set -euo pipefail
cargo run --bin apfsc_qualify -- --root .apfsc --mode release
