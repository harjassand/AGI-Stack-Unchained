#!/usr/bin/env bash
set -euo pipefail
cargo test --quiet proptest
cargo test --quiet --test loom_prod_leases --test loom_prod_activation
