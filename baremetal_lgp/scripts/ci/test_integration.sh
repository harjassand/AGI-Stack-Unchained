#!/usr/bin/env bash
set -euo pipefail
cargo test -q apfsc_phase
cargo test --quiet --test apfsc_prod_e2e_daemon --test apfsc_prod_e2e_crash_resume --test apfsc_prod_e2e_release_qual
