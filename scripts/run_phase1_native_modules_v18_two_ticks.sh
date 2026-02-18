#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUN_ID="${RUN_ID:-phase1_native_modules_v18_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR_TMPL="${ROOT}/runs/${RUN_ID}/tick_{tick:04d}"

mkdir -p "${ROOT}/runs/${RUN_ID}"

export PYTHONPATH="${ROOT}/CDEL-v2:${ROOT}${PYTHONPATH+:$PYTHONPATH}"
export OMEGA_META_CORE_ACTIVATION_MODE="${OMEGA_META_CORE_ACTIVATION_MODE:-simulate}"
export OMEGA_ALLOW_SIMULATE_ACTIVATION="${OMEGA_ALLOW_SIMULATE_ACTIVATION:-1}"
export OMEGA_NATIVE_CANON_BYTES="${OMEGA_NATIVE_CANON_BYTES:-1}"

python3 -m orchestrator.rsi_omega_daemon_v18_0 \
  --campaign_pack "${ROOT}/campaigns/rsi_omega_daemon_v18_0_phase1_native_modules_v1/rsi_omega_daemon_pack_v1.json" \
  --out_dir "${OUT_DIR_TMPL}" \
  --mode loop \
  --tick_u64 1 \
  --ticks 2

echo
echo "Run dir: runs/${RUN_ID}"
echo "Tick 1 dispatch dir: ${ROOT}/runs/${RUN_ID}/tick_0001/daemon/rsi_omega_daemon_v18_0/state/dispatch"
echo "Tick 2 native stats: ${ROOT}/runs/${RUN_ID}/tick_0002/daemon/rsi_omega_daemon_v18_0/state/ledger/native"

