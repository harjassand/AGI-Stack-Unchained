#!/usr/bin/env bash
set -euo pipefail
cargo test --quiet apfsc_prod_telemetry
cargo test --quiet apfsc_prod_release_manifest
