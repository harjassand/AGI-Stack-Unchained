#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git submodule update --init --recursive

RUNS_ROOT="${RUNS_ROOT:-runs}"
SEGMENT_HOURS="${SEGMENT_HOURS:-6}"
SERIES_BASE="${SERIES_BASE:-omega_unified_wild_$(date -u +%Y%m%d_%H%M%S)}"
PROMO_FOCUS="${PROMO_FOCUS:-1}"
OMEGA_CAMPAIGN_PACK="${OMEGA_CAMPAIGN_PACK:-campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json}"
OMEGA_COORDINATOR_MODULE="${OMEGA_COORDINATOR_MODULE:-orchestrator.omega_v18_0.coordinator_v1}"
OMEGA_STATE_DIR_REL="${OMEGA_STATE_DIR_REL:-daemon/rsi_omega_daemon_v18_0/state}"

GE_MAX_CCAPS="${GE_MAX_CCAPS:-6}"
POLYMATH_SCOUT_EVERY_TICKS="${POLYMATH_SCOUT_EVERY_TICKS:-2}"
POLYMATH_MAX_NEW_DOMAINS_PER_RUN="${POLYMATH_MAX_NEW_DOMAINS_PER_RUN:-4}"
POLYMATH_CONQUER_BUDGET_TICKS="${POLYMATH_CONQUER_BUDGET_TICKS:-20}"
SPEED_CHURN_DEEMPHASIS="${SPEED_CHURN_DEEMPHASIS:-0}"
ZERO_FRONTIER_SEGMENTS_U64=0

export PYTHONPATH="$ROOT:$ROOT/CDEL-v2:${PYTHONPATH:-}"
export OMEGA_BLACKBOX="${OMEGA_BLACKBOX:-1}"
export OMEGA_NET_LIVE_OK="${OMEGA_NET_LIVE_OK:-1}"
export OMEGA_WILD_MODE="${OMEGA_WILD_MODE:-1}"
export ORCH_LLM_LIVE_OK="${ORCH_LLM_LIVE_OK:-1}"
export ORCH_LLM_BACKEND="${ORCH_LLM_BACKEND:-openai}"
export ORCH_LLM_TEMPERATURE="${ORCH_LLM_TEMPERATURE:-0.7}"
export ORCH_LLM_MAX_TOKENS="${ORCH_LLM_MAX_TOKENS:-1600}"
export OMEGA_SH1_SCAFFOLD_ENABLE="${OMEGA_SH1_SCAFFOLD_ENABLE:-1}"
export OMEGA_SH1_SCAFFOLD_DOMAINS="${OMEGA_SH1_SCAFFOLD_DOMAINS:-frontier_probe}"
ORCH_LLM_REPLAY_PATH_USER_SET=0
if [[ -n "${ORCH_LLM_REPLAY_PATH:-}" ]]; then
  ORCH_LLM_REPLAY_PATH_USER_SET=1
fi

case "${ORCH_LLM_BACKEND}" in
  openai|openai_harvest)
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
      echo "missing OPENAI_API_KEY for ORCH_LLM_BACKEND=${ORCH_LLM_BACKEND}" >&2
      exit 1
    fi
    ;;
  anthropic|anthropic_harvest)
    if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
      echo "missing ANTHROPIC_API_KEY for ORCH_LLM_BACKEND=${ORCH_LLM_BACKEND}" >&2
      exit 1
    fi
    ;;
  *)
    :
    ;;
esac

CONTROL_DIR="$ROOT/$RUNS_ROOT/${SERIES_BASE}__wild_controller"
mkdir -p "$CONTROL_DIR"
SEGMENT_SUMMARY_JSONL="$CONTROL_DIR/OMEGA_WILD_SEGMENT_SUMMARY_v1.jsonl"
touch "$SEGMENT_SUMMARY_JSONL"

echo "WILD_CONTROLLER_DIR=$CONTROL_DIR"
echo "SEGMENT_SUMMARY_JSONL=$SEGMENT_SUMMARY_JSONL"

segment_u64=0
while true; do
  segment_u64=$((segment_u64 + 1))
  segment_id="$(printf '%s_seg_%04d' "$SERIES_BASE" "$segment_u64")"
  run_dir_pre="$ROOT/$RUNS_ROOT/$segment_id"
  if [[ "$ORCH_LLM_REPLAY_PATH_USER_SET" -eq 0 ]]; then
    export ORCH_LLM_REPLAY_PATH="$run_dir_pre/_overnight_pack/replay/orch_llm_replay.jsonl"
  fi
  export OMEGA_PREV_ZERO_FRONTIER_SEGMENTS_U64="$ZERO_FRONTIER_SEGMENTS_U64"

  echo ""
  echo "=== WILD SEGMENT $segment_u64 :: $segment_id ==="
  echo "knobs ge_max_ccaps=$GE_MAX_CCAPS polymath_scout_every_ticks=$POLYMATH_SCOUT_EVERY_TICKS polymath_max_new_domains_per_run=$POLYMATH_MAX_NEW_DOMAINS_PER_RUN speed_churn_deemphasis=$SPEED_CHURN_DEEMPHASIS"

  RUNNER_OUT="$(
    python3 tools/omega/omega_overnight_runner_v1.py \
      --hours "$SEGMENT_HOURS" \
      --series_prefix "$segment_id" \
      --runs_root "$RUNS_ROOT" \
      --profile unified \
      --meta_core_mode sandbox \
      --campaign_pack "$OMEGA_CAMPAIGN_PACK" \
      --coordinator_module "$OMEGA_COORDINATOR_MODULE" \
      --state_dir_rel "$OMEGA_STATE_DIR_REL" \
      --enable_ge_sh1_optimizer 1 \
      --enable_llm_router 1 \
      --ge_max_ccaps "$GE_MAX_CCAPS" \
      --enable_polymath_drive 1 \
      --polymath_scout_every_ticks "$POLYMATH_SCOUT_EVERY_TICKS" \
      --polymath_max_new_domains_per_run "$POLYMATH_MAX_NEW_DOMAINS_PER_RUN" \
      --polymath_conquer_budget_ticks "$POLYMATH_CONQUER_BUDGET_TICKS" \
      --promo_focus "$PROMO_FOCUS" \
      --speed_churn_deemphasis "$SPEED_CHURN_DEEMPHASIS"
  )"

  REPORT_JSON="$(printf '%s\n' "$RUNNER_OUT" | sed -n '1p')"
  if [[ -z "$REPORT_JSON" || ! -f "$REPORT_JSON" ]]; then
    echo "runner did not emit a valid report path; output follows:" >&2
    printf '%s\n' "$RUNNER_OUT" >&2
    exit 1
  fi
  RUN_DIR="$(cd "$(dirname "$REPORT_JSON")" && pwd)"

  SUMMARY_ENV="$(
    python3 - "$REPORT_JSON" "$SEGMENT_SUMMARY_JSONL" <<'PY'
import json
import pathlib
import sys

report_path = pathlib.Path(sys.argv[1]).resolve()
summary_jsonl = pathlib.Path(sys.argv[2]).resolve()
run_dir = report_path.parent

def load_json(path: pathlib.Path) -> dict:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

report = load_json(report_path)
promotion = load_json(run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json")
usage = load_json(run_dir / "OMEGA_CAPABILITY_USAGE_v1.json")
frontier = report.get("capability_frontier") if isinstance(report, dict) else {}
frontier = frontier if isinstance(frontier, dict) else {}
final_frontier = frontier.get("final") if isinstance(frontier.get("final"), dict) else {}
next_pressure = report.get("next_segment_pressure") if isinstance(report, dict) else {}
next_pressure = next_pressure if isinstance(next_pressure, dict) else {}

dispatch_rows = usage.get("dispatch_counts_by_campaign")
dispatch_rows = dispatch_rows if isinstance(dispatch_rows, list) else []
dispatch_counts = []
for row in dispatch_rows:
    if not isinstance(row, dict):
        continue
    campaign_id = str(row.get("campaign_id", "")).strip()
    dispatch_u64 = int(row.get("dispatch_u64", 0))
    if campaign_id and dispatch_u64 > 0:
        dispatch_counts.append((campaign_id, dispatch_u64))
dispatch_counts.sort(key=lambda item: (-item[1], item[0]))
dispatch_hist = ",".join(f"{campaign_id}:{count}" for campaign_id, count in dispatch_counts[:12]) or "(none)"

new_caps = frontier.get("newly_activated_capability_ids_last_W_ticks")
if not isinstance(new_caps, list):
    new_caps = final_frontier.get("newly_activated_capability_ids_last_W_ticks", [])
new_caps = [str(row).strip() for row in new_caps if str(row).strip()]
new_caps_line = ",".join(sorted(new_caps)) if new_caps else "(none)"

summary_row = {
    "schema_version": "OMEGA_WILD_SEGMENT_SUMMARY_ROW_v1",
    "series_prefix": str(report.get("series_prefix", "")),
    "run_dir": run_dir.as_posix(),
    "promoted_u64": int(promotion.get("promoted_u64", 0)),
    "rejected_u64": int(promotion.get("rejected_u64", 0)),
    "cap_frontier_u64": int(frontier.get("cap_frontier_u64", final_frontier.get("cap_frontier_u64", 0))),
    "cap_enabled_u64": int(frontier.get("cap_enabled_u64", final_frontier.get("cap_enabled_u64", 0))),
    "cap_activated_u64": int(frontier.get("cap_activated_u64", final_frontier.get("cap_activated_u64", 0))),
    "frontier_delta_u64": int(frontier.get("frontier_delta_u64", 0)),
    "dispatch_histogram": dispatch_hist,
    "newly_activated_capability_ids": sorted(new_caps),
    "next_segment_pressure": next_pressure,
}
with summary_jsonl.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(summary_row, sort_keys=True, separators=(",", ":")) + "\n")

print(
    "SEGMENT_SUMMARY "
    f"promoted_u64={summary_row['promoted_u64']} "
    f"rejected_u64={summary_row['rejected_u64']} "
    f"cap_frontier_u64={summary_row['cap_frontier_u64']} "
    f"cap_enabled_u64={summary_row['cap_enabled_u64']} "
    f"cap_activated_u64={summary_row['cap_activated_u64']} "
    f"frontier_delta_u64={summary_row['frontier_delta_u64']}"
)
print(f"DISPATCH_HISTOGRAM {dispatch_hist}")
print(f"NEWLY_ACTIVATED_CAPABILITY_IDS {new_caps_line}")
print(
    "NEXT_PRESSURE "
    f"auto_escalated_b={bool(next_pressure.get('auto_escalated_b', False))} "
    f"recommended_ge_max_ccaps_u64={int(next_pressure.get('recommended_ge_max_ccaps_u64', 0))} "
    f"recommended_polymath_scout_every_ticks_u64={int(next_pressure.get('recommended_polymath_scout_every_ticks_u64', 0))} "
    f"recommended_speed_churn_deemphasis_b={bool(next_pressure.get('recommended_speed_churn_deemphasis_b', False))}"
)
print(f"NEXT_GE_MAX_CCAPS={int(next_pressure.get('recommended_ge_max_ccaps_u64', 0))}")
print(f"NEXT_SCOUT_EVERY={int(next_pressure.get('recommended_polymath_scout_every_ticks_u64', 0))}")
print(f"NEXT_MAX_NEW_DOMAINS={int(next_pressure.get('recommended_polymath_max_new_domains_per_run_u64', 0))}")
print(f"NEXT_SPEED_DEEMPHASIS={1 if bool(next_pressure.get('recommended_speed_churn_deemphasis_b', False)) else 0}")
print(f"NEXT_ZERO_FRONTIER_SEGMENTS={int(next_pressure.get('zero_frontier_segments_u64', 0))}")
PY
  )"

  printf '%s\n' "$SUMMARY_ENV" | sed -n '1,4p'

  NEXT_GE_MAX_CCAPS="$(printf '%s\n' "$SUMMARY_ENV" | awk -F= '/^NEXT_GE_MAX_CCAPS=/{print $2}' | tail -n 1)"
  NEXT_SCOUT_EVERY="$(printf '%s\n' "$SUMMARY_ENV" | awk -F= '/^NEXT_SCOUT_EVERY=/{print $2}' | tail -n 1)"
  NEXT_MAX_NEW_DOMAINS="$(printf '%s\n' "$SUMMARY_ENV" | awk -F= '/^NEXT_MAX_NEW_DOMAINS=/{print $2}' | tail -n 1)"
  NEXT_SPEED_DEEMPHASIS="$(printf '%s\n' "$SUMMARY_ENV" | awk -F= '/^NEXT_SPEED_DEEMPHASIS=/{print $2}' | tail -n 1)"
  NEXT_ZERO_FRONTIER_SEGMENTS="$(printf '%s\n' "$SUMMARY_ENV" | awk -F= '/^NEXT_ZERO_FRONTIER_SEGMENTS=/{print $2}' | tail -n 1)"

  if [[ -n "$NEXT_GE_MAX_CCAPS" && "$NEXT_GE_MAX_CCAPS" -ge 1 ]]; then
    GE_MAX_CCAPS="$NEXT_GE_MAX_CCAPS"
  fi
  if [[ -n "$NEXT_SCOUT_EVERY" && "$NEXT_SCOUT_EVERY" -ge 1 ]]; then
    POLYMATH_SCOUT_EVERY_TICKS="$NEXT_SCOUT_EVERY"
  fi
  if [[ -n "$NEXT_MAX_NEW_DOMAINS" && "$NEXT_MAX_NEW_DOMAINS" -ge 0 ]]; then
    POLYMATH_MAX_NEW_DOMAINS_PER_RUN="$NEXT_MAX_NEW_DOMAINS"
  fi
  if [[ -n "$NEXT_SPEED_DEEMPHASIS" ]]; then
    SPEED_CHURN_DEEMPHASIS="$NEXT_SPEED_DEEMPHASIS"
  fi
  if [[ -n "$NEXT_ZERO_FRONTIER_SEGMENTS" ]]; then
    ZERO_FRONTIER_SEGMENTS_U64="$NEXT_ZERO_FRONTIER_SEGMENTS"
  fi

  echo "SEGMENT_RUN_DIR=$RUN_DIR"
done
