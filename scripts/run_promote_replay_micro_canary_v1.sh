#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

python3 scripts/run_long_disciplined_loop_v1.py \
  --campaign_pack campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json \
  --run_root runs/long_promote_replay_micro_canary_v1 \
  --max_ticks 15 \
  --stop_on_first_heavy_promoted true \
  --soak_after_first_heavy_promoted_ticks 3 \
  --stop_on_probe_missing true \
  --stop_on_state_verifier_invalid true \
  "$@"
