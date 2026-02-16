#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git submodule update --init --recursive

SERIES_PREFIX="${SERIES_PREFIX:-omega_unified_30min_$(date -u +%Y%m%d_%H%M%S)}"
RUNS_ROOT="${RUNS_ROOT:-runs}"
RUN_DIR_PRE="$ROOT/$RUNS_ROOT/$SERIES_PREFIX"
export PYTHONPATH="$ROOT:$ROOT/CDEL-v2:${PYTHONPATH:-}"
export OMEGA_NET_LIVE_OK="${OMEGA_NET_LIVE_OK:-1}"
export ORCH_LLM_BACKEND="${ORCH_LLM_BACKEND:-mock}"
export ORCH_LLM_REPLAY_PATH="${ORCH_LLM_REPLAY_PATH:-$RUN_DIR_PRE/_overnight_pack/replay/orch_llm_replay.jsonl}"
if [[ -z "${ORCH_LLM_MOCK_RESPONSE:-}" ]]; then
  export ORCH_LLM_MOCK_RESPONSE='{"schema_version":"omega_llm_router_plan_v1","created_at_utc":"","created_from_tick_u64":0,"web_queries":[{"provider":"wikipedia","query":"OpenAI","top_k":2}],"goal_injections":[{"capability_id":"RSI_SAS_METASEARCH","goal_id":"goal_auto_llm_router_0001","priority_u8":5,"reason":"llm-router-smoke"}]}'
fi

RUNNER_OUT="$(
  python3 tools/omega/omega_overnight_runner_v1.py \
    --hours 0.5 \
    --series_prefix "$SERIES_PREFIX" \
    --runs_root "$RUNS_ROOT" \
    --profile unified \
    --meta_core_mode sandbox \
    --campaign_pack campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json \
    --enable_ge_sh1_optimizer 1 \
    --enable_llm_router 1 \
    --ge_max_ccaps 3 \
    --enable_polymath_drive 1 \
    --polymath_scout_every_ticks 3 \
    --polymath_max_new_domains_per_run 2 \
    --polymath_conquer_budget_ticks 10 \
    --promo_focus 1
)"

REPORT_JSON="$(printf '%s\n' "$RUNNER_OUT" | sed -n '1p')"
if [[ -z "$REPORT_JSON" ]]; then
  echo "runner did not emit OMEGA_OVERNIGHT_REPORT_v1.json path" >&2
  exit 1
fi
RUN_DIR="$(cd "$(dirname "$REPORT_JSON")" && pwd)"
RUN_ID="$(basename "$RUN_DIR")"

echo "RUN_ID=$RUN_ID"
echo "RUN_DIR=$RUN_DIR"

python3 - "$RUN_DIR" <<'PY'
import json
import pathlib
import sys

run_dir = pathlib.Path(sys.argv[1]).resolve()
promotion_path = run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json"
gates_path = run_dir / "OMEGA_BENCHMARK_GATES_v1.json"
usage_path = run_dir / "OMEGA_CAPABILITY_USAGE_v1.json"

promotion = json.loads(promotion_path.read_text(encoding="utf-8")) if promotion_path.exists() else {}
gates = json.loads(gates_path.read_text(encoding="utf-8")) if gates_path.exists() else {}
usage = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {}

gate_status = {}
if isinstance(gates, dict):
    gate_rows = gates.get("gates")
    if isinstance(gate_rows, dict):
        for gate, row in gate_rows.items():
            if isinstance(row, dict):
                gate_status[str(gate)] = str(row.get("status", ""))

dispatch_caps = []
if isinstance(usage, dict):
    rows = usage.get("dispatch_counts_by_capability")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                capability_id = str(row.get("capability_id", "")).strip()
                dispatch_u64 = int(row.get("dispatch_u64", 0))
                if capability_id and dispatch_u64 > 0:
                    dispatch_caps.append(f"{capability_id}:{dispatch_u64}")

evidence_errors = usage.get("evidence_errors") if isinstance(usage, dict) else []
print(
    "PROMOTION "
    f"promoted_u64={int(promotion.get('promoted_u64', 0))} "
    f"rejected_u64={int(promotion.get('rejected_u64', 0))} "
    f"skipped_u64={int(promotion.get('skipped_u64', 0))}"
)
print(
    "GATES "
    f"B={gate_status.get('B', '')} "
    f"P={gate_status.get('P', '')} "
    f"Q={gate_status.get('Q', '')}"
)
print(
    "USAGE "
    f"ok_b={bool(usage.get('ok_b', False)) if isinstance(usage, dict) else False} "
    f"evidence_errors_u64={len(evidence_errors) if isinstance(evidence_errors, list) else 0} "
    f"dispatch_caps_u64={len(dispatch_caps)}"
)
if dispatch_caps:
    print("DISPATCH_CAPS " + ",".join(sorted(dispatch_caps)))
print("PROMOTION_SUMMARY_JSON " + promotion_path.as_posix())
print("BENCHMARK_GATES_JSON " + gates_path.as_posix())
print("CAPABILITY_USAGE_JSON " + usage_path.as_posix())
PY
