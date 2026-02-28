#!/usr/bin/env bash
set -euo pipefail
cargo test -q apfsc_prod_e2e_crash_resume
