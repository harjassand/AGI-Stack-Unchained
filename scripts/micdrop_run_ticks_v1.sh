#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

N_TICKS="${N_TICKS:-50}"
CAMPAIGN_PACK="campaigns/rsi_omega_daemon_v19_0_micdrop_v1/rsi_omega_daemon_pack_v1.json"
PREV_STATE_DIR=""

export PYTHONPATH=".:CDEL-v2:Extension-1/agi-orchestrator"
export OMEGA_AUTHORITY_PINS_REL="authority/authority_pins_micdrop_v1.json"
export OMEGA_CCAP_PATCH_ALLOWLISTS_REL="authority/ccap_patch_allowlists_micdrop_v1.json"
export OMEGA_META_CORE_ACTIVATION_MODE="live"
export OMEGA_ALLOW_SIMULATE_ACTIVATION="0"
export OMEGA_DISABLE_FORCED_RUNAWAY="1"
export OMEGA_CCAP_ALLOW_DIRTY_TREE="1"

for TICK in $(seq 1 "$N_TICKS"); do
  OUT_DIR="runs/micdrop_ticks/tick_${TICK}"
  mkdir -p "$OUT_DIR"

  cmd=(
    python3 -m orchestrator.rsi_omega_daemon_v19_0
    --campaign_pack "$CAMPAIGN_PACK"
    --out_dir "$OUT_DIR"
    --mode once
    --tick_u64 "$TICK"
  )
  if [[ -n "$PREV_STATE_DIR" ]]; then
    cmd+=(--prev_state_dir "$PREV_STATE_DIR")
  fi

  "${cmd[@]}"
  PREV_STATE_DIR="$OUT_DIR/daemon/rsi_omega_daemon_v19_0/state"

done
