#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

T="${1:-20}"
PACK="${OMEGA_PACK:-campaigns/rsi_omega_daemon_v18_0/rsi_omega_daemon_pack_v1.json}"
RUN_PREFIX="${OMEGA_RUN_PREFIX:-rsi_omega_daemon_v18_0_tick_}"
PREV_STATE_DIR=""

for tick in $(seq 1 "$T"); do
  tick_id="$(printf "%04d" "$tick")"
  out_dir="runs/${RUN_PREFIX}${tick_id}"
  rm -rf "$out_dir"

  cmd=(
    python3 -m orchestrator.rsi_omega_daemon_v18_0
    --campaign_pack "$PACK"
    --out_dir "$out_dir"
    --mode once
    --tick_u64 "$tick"
  )
  if [[ -n "$PREV_STATE_DIR" ]]; then
    cmd+=(--prev_state_dir "$PREV_STATE_DIR")
  fi

  PYTHONPATH="CDEL-v2:Extension-1/agi-orchestrator:." OMEGA_META_CORE_ACTIVATION_MODE="live" "${cmd[@]}"

  state_dir="$out_dir/daemon/rsi_omega_daemon_v18_0/state"
  PYTHONPATH="CDEL-v2:." python3 -m cdel.v18_0.verify_rsi_omega_daemon_v1 \
    --mode full \
    --state_dir "$state_dir"

  action_kind="$(PYTHONPATH="CDEL-v2:." python3 - "$state_dir" <<'PY'
import json
import sys
from pathlib import Path
state_dir = Path(sys.argv[1])
rows = sorted((state_dir / "decisions").glob("sha256_*.omega_decision_plan_v1.json"))
if not rows:
    print("SAFE_HALT")
else:
    obj = json.loads(rows[-1].read_text(encoding="utf-8"))
    print(obj.get("action_kind", "SAFE_HALT"))
PY
)"

  PREV_STATE_DIR="$state_dir"
  if [[ "$action_kind" == "SAFE_HALT" ]]; then
    echo "SAFE_HALT at tick=$tick"
    break
  fi

done
