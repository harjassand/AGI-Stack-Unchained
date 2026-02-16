#!/usr/bin/env bash
set -u -o pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TICKS=100
CAMPAIGN_PACK="campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json"
OUT_ROOT="runs/rsi_omega_runaway_v18_1"
TMP_LOG_DIR="${TMPDIR:-/tmp}/omega_runaway_weekend_v18_1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ticks)
      TICKS="$2"
      shift 2
      ;;
    --campaign_pack)
      CAMPAIGN_PACK="$2"
      shift 2
      ;;
    --out_root)
      OUT_ROOT="$2"
      shift 2
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$TMP_LOG_DIR" "$OUT_ROOT"

RESULT_JSON="$OUT_ROOT/OMEGA_WEEKEND_RESULT_v1.json"
FUSE_FILE="$OUT_ROOT/run_fail_count_u64.json"
SAFE_HALT_FILE="$OUT_ROOT/SAFE_HALT"

PREV_STATE_DIR=""
ticks_completed=0
invalid_tick_u64=""
invalid_reason=""

run_step_capture() {
  local step_log="$1"
  shift
  if [[ "${OMEGA_WEEKEND_VERBOSE:-0}" == "1" ]]; then
    "$@" | tee "$step_log"
    return "${PIPESTATUS[0]}"
  fi
  "$@" >"$step_log" 2>&1
}

extract_invalid_reason() {
  local verify_log="$1"
  python3 - "$verify_log" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
reason = ""
if path.exists():
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("INVALID:"):
            reason = line.split(":", 1)[1].strip()
if reason:
    print(reason)
PY
}

reset_fail_fuse() {
  python3 - "$FUSE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema_version": "omega_weekend_fail_fuse_v1",
    "last_failed_tick_u64": None,
    "run_fail_count_u64": 0,
    "last_failure_reason": None,
}
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

update_fail_fuse() {
  local tick_u64="$1"
  local reason="$2"
  python3 - "$FUSE_FILE" "$tick_u64" "$reason" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
tick_u64 = int(sys.argv[2])
reason = str(sys.argv[3])

payload = {
    "schema_version": "omega_weekend_fail_fuse_v1",
    "last_failed_tick_u64": None,
    "run_fail_count_u64": 0,
    "last_failure_reason": None,
}
if path.exists():
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            payload.update(raw)
    except Exception:
        pass

last_tick = payload.get("last_failed_tick_u64")
if isinstance(last_tick, int) and last_tick == tick_u64:
    count = int(payload.get("run_fail_count_u64", 0)) + 1
else:
    count = 1

payload = {
    "schema_version": "omega_weekend_fail_fuse_v1",
    "last_failed_tick_u64": tick_u64,
    "run_fail_count_u64": int(count),
    "last_failure_reason": reason,
}
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
print(int(count))
PY
}

read_fail_count() {
  python3 - "$FUSE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print(0)
    raise SystemExit(0)
try:
    raw = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print(0)
    raise SystemExit(0)
if not isinstance(raw, dict):
    print(0)
    raise SystemExit(0)
print(int(raw.get("run_fail_count_u64", 0)))
PY
}

compute_summary_metrics() {
  OMEGA_WEEKEND_TICKS_COMPLETED="$1" \
  OMEGA_WEEKEND_TICKS_REQUESTED="$2" \
  OMEGA_WEEKEND_OUT_ROOT="$OUT_ROOT" \
  python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

Q32_ONE = 1 << 32
RATIO_30 = (13 * Q32_ONE) // 10

ticks_completed = int(os.environ["OMEGA_WEEKEND_TICKS_COMPLETED"])
ticks_requested = int(os.environ["OMEGA_WEEKEND_TICKS_REQUESTED"])
out_root = str(os.environ["OMEGA_WEEKEND_OUT_ROOT"])

summary = {
    "ticks_requested": ticks_requested,
    "ticks_completed": ticks_completed,
    "best_metric_id": "",
    "best_improve_ratio_q32": 0,
    "any_30pct_improvement": False,
    "promotions": 0,
    "activations": 0,
    "start_version_minor_u64": 0,
    "end_version_minor_u64": 0,
}

if ticks_completed <= 0:
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0)

runs = []
for tick in range(1, ticks_completed + 1):
    run_dir = Path(f"{out_root}_tick_{tick:04d}")
    if not run_dir.is_dir():
        print(f"missing run dir: {run_dir}", file=sys.stderr)
        raise SystemExit(7)
    runs.append(run_dir)

first_runaway_dir = runs[0] / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "runaway"
last_runaway_dir = runs[-1] / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "runaway"

first_states = []
for path in sorted(first_runaway_dir.glob("sha256_*.omega_runaway_state_v1.json")):
    first_states.append(json.loads(path.read_text(encoding="utf-8")))
if not first_states:
    print("missing initial runaway state", file=sys.stderr)
    raise SystemExit(8)

last_states = []
for path in sorted(last_runaway_dir.glob("sha256_*.omega_runaway_state_v1.json")):
    last_states.append(json.loads(path.read_text(encoding="utf-8")))
if not last_states:
    print("missing final runaway state", file=sys.stderr)
    raise SystemExit(9)

start_state = min(first_states, key=lambda row: int(row.get("tick_u64", 1 << 60)))
end_state = max(last_states, key=lambda row: int(row.get("tick_u64", -1)))
summary["start_version_minor_u64"] = int(start_state.get("version_minor_u64", 0))
summary["end_version_minor_u64"] = int(end_state.get("version_minor_u64", 0))

start_metrics = start_state.get("metric_states")
end_metrics = end_state.get("metric_states")
if not isinstance(start_metrics, dict) or not isinstance(end_metrics, dict):
    print("invalid runaway metric states", file=sys.stderr)
    raise SystemExit(10)

best_metric = ""
best_ratio_q32 = 0
any_30 = False
for metric_id, start_row in sorted(start_metrics.items()):
    if not isinstance(start_row, dict):
        continue
    end_row = end_metrics.get(metric_id)
    if not isinstance(end_row, dict):
        continue
    start_q = int(((start_row.get("last_value_q32") or {}).get("q", 0)))
    best_q = int(((end_row.get("best_value_q32") or {}).get("q", 0)))
    if start_q <= 0 or best_q <= 0:
        continue
    ratio_q32 = (start_q << 32) // best_q
    if ratio_q32 >= RATIO_30:
        any_30 = True
    if ratio_q32 > best_ratio_q32:
        best_ratio_q32 = ratio_q32
        best_metric = metric_id

summary["best_metric_id"] = best_metric
summary["best_improve_ratio_q32"] = int(best_ratio_q32)
summary["any_30pct_improvement"] = bool(any_30)

promotions = 0
activations = 0
for run in runs:
    state_dir = run / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    for path in sorted(state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if str((payload.get("result") or {}).get("status")) == "PROMOTED":
            promotions += 1
    for path in sorted(state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if bool(payload.get("activation_success", False)):
            activations += 1

summary["promotions"] = int(promotions)
summary["activations"] = int(activations)

print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
PY
}

write_result_json() {
  local pass_value="$1"
  local reason_value="$2"
  local summary_json="${3:-{}}"
  RESULT_PATH="$RESULT_JSON" \
  RESULT_PASS="$pass_value" \
  RESULT_REASON="$reason_value" \
  RESULT_TICKS_REQUESTED="$TICKS" \
  RESULT_TICKS_COMPLETED="$ticks_completed" \
  RESULT_INVALID_TICK="$invalid_tick_u64" \
  RESULT_INVALID_REASON="$invalid_reason" \
  RESULT_SUMMARY_JSON="$summary_json" \
  RESULT_FAIL_FUSE_FILE="$FUSE_FILE" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

result_path = Path(os.environ["RESULT_PATH"])
pass_value = str(os.environ["RESULT_PASS"]).strip().lower() == "true"
reason = str(os.environ["RESULT_REASON"])
ticks_requested = int(os.environ["RESULT_TICKS_REQUESTED"])
ticks_completed = int(os.environ["RESULT_TICKS_COMPLETED"])
invalid_tick_raw = str(os.environ.get("RESULT_INVALID_TICK", "")).strip()
invalid_reason_raw = str(os.environ.get("RESULT_INVALID_REASON", "")).strip()
summary_raw = str(os.environ.get("RESULT_SUMMARY_JSON", "{}"))
fuse_file = Path(os.environ["RESULT_FAIL_FUSE_FILE"])

try:
    summary = json.loads(summary_raw)
except Exception:
    summary = {}
if not isinstance(summary, dict):
    summary = {}

fail_count = 0
if fuse_file.exists():
    try:
        fuse_payload = json.loads(fuse_file.read_text(encoding="utf-8"))
        if isinstance(fuse_payload, dict):
            fail_count = int(fuse_payload.get("run_fail_count_u64", 0))
    except Exception:
        fail_count = 0

invalid_tick = int(invalid_tick_raw) if invalid_tick_raw else None
invalid_reason = invalid_reason_raw if invalid_reason_raw else None

payload = {
    "schema_version": "OMEGA_WEEKEND_RESULT_v1",
    "pass": bool(pass_value),
    "reason": reason,
    "ticks_requested": ticks_requested,
    "ticks_completed": ticks_completed,
    "invalid_tick_u64": invalid_tick,
    "invalid_reason": invalid_reason,
    "run_fail_count_u64": int(fail_count),
    "summary": summary,
}
result_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

structural_fail() {
  local reason="$1"
  local detail_json="${2:-{}}"
  write_result_json "false" "$reason" "$detail_json"
  echo "OMEGA_WEEKEND: STRUCTURAL_FAIL reason=${reason} ticks_completed=${ticks_completed}/${TICKS}" >&2
  exit 1
}

if [[ -f "$SAFE_HALT_FILE" ]]; then
  write_result_json "false" "SAFE_HALT_PREEXISTING" "{}"
  echo "OMEGA_WEEKEND: HALT reason=SAFE_HALT_PREEXISTING ticks_completed=${ticks_completed}/${TICKS}"
  exit 0
fi

for tick in $(seq 1 "$TICKS"); do
  tick_id="$(printf '%04d' "$tick")"
  out_dir="${OUT_ROOT}_tick_${tick_id}"
  rm -rf "$out_dir"
  daemon_log="$TMP_LOG_DIR/tick_${tick_id}.daemon.log"
  verify_log="$TMP_LOG_DIR/tick_${tick_id}.verify.log"

  cmd=(
    python3 -m orchestrator.rsi_omega_daemon_v18_0
    --campaign_pack "$CAMPAIGN_PACK"
    --out_dir "$out_dir"
    --mode once
    --tick_u64 "$tick"
  )
  if [[ -n "$PREV_STATE_DIR" ]]; then
    cmd+=(--prev_state_dir "$PREV_STATE_DIR")
  fi

  if ! run_step_capture "$daemon_log" \
    env \
      PYTHONPATH="CDEL-v2:Extension-1/agi-orchestrator:." \
      OMEGA_META_CORE_ACTIVATION_MODE="${OMEGA_META_CORE_ACTIVATION_MODE:-live}" \
      OMEGA_ALLOW_SIMULATE_ACTIVATION="${OMEGA_ALLOW_SIMULATE_ACTIVATION:-1}" \
      OMEGA_EXEC_WORKSPACE_NAMESPACE="$OUT_ROOT" \
      "${cmd[@]}"; then
    structural_fail "DAEMON_CRASH" "{\"tick_u64\":${tick}}"
  fi

  state_dir="$out_dir/daemon/rsi_omega_daemon_v18_0/state"
  if [[ ! -d "$state_dir" ]]; then
    structural_fail "MISSING_STATE_DIR" "{\"tick_u64\":${tick}}"
  fi
  if ! compgen -G "$state_dir/snapshot/sha256_*.omega_tick_snapshot_v1.json" >/dev/null; then
    structural_fail "MISSING_TICK_SNAPSHOT" "{\"tick_u64\":${tick}}"
  fi

  if run_step_capture "$verify_log" \
    env \
      PYTHONPATH="CDEL-v2:." \
      python3 -m cdel.v18_0.verify_rsi_omega_daemon_v1 --mode full --state_dir "$state_dir"; then
    : > "$state_dir/TICK_OK"
    rm -f "$state_dir/TICK_FAIL"
    PREV_STATE_DIR="$state_dir"
    ticks_completed="$tick"
    reset_fail_fuse
    continue
  fi

  : > "$state_dir/TICK_FAIL"
  rm -f "$state_dir/TICK_OK"
  invalid_tick_u64="$tick"
  invalid_reason="$(extract_invalid_reason "$verify_log")"

  if [[ -z "$invalid_reason" ]]; then
    structural_fail "VERIFIER_CRASH" "{\"tick_u64\":${tick}}"
  fi
  if [[ "$invalid_reason" == "TRACE_HASH_MISMATCH" ]]; then
    structural_fail "TRACE_HASH_MISMATCH" "{\"tick_u64\":${tick}}"
  fi

  fail_count="$(update_fail_fuse "$tick" "$invalid_reason")"
  if [[ "$fail_count" -gt 3 ]]; then
    printf 'SAFE_HALT tick_u64=%s reason=%s run_fail_count_u64=%s\n' "$tick" "$invalid_reason" "$fail_count" > "$SAFE_HALT_FILE"
    write_result_json "false" "SAFE_HALT_CRASH_LOOP" "{\"tick_u64\":${tick},\"run_fail_count_u64\":${fail_count}}"
    echo "OMEGA_WEEKEND: HALT reason=SAFE_HALT_CRASH_LOOP tick=${tick} run_fail_count_u64=${fail_count}"
    exit 0
  fi

  write_result_json "false" "INVALID_TICK" "{\"tick_u64\":${tick},\"invalid_reason\":\"${invalid_reason}\",\"run_fail_count_u64\":${fail_count}}"
  echo "OMEGA_WEEKEND: HALT reason=INVALID_TICK tick=${tick} invalid_reason=${invalid_reason}"
  exit 0
done

summary_json="$(compute_summary_metrics "$ticks_completed" "$TICKS")" || structural_fail "SUMMARY_COMPUTE_FAIL" "{}"
has_30pct="$(SUMMARY_JSON="$summary_json" python3 - <<'PY'
import json
import os

obj = json.loads(os.environ["SUMMARY_JSON"])
print("1" if bool(obj.get("any_30pct_improvement", False)) else "0")
PY
)"

if [[ "$has_30pct" != "1" ]]; then
  write_result_json "false" "NO_30PCT_IMPROVEMENT" "$summary_json"
  echo "OMEGA_WEEKEND: COMPLETE pass=false reason=NO_30PCT_IMPROVEMENT ticks=${ticks_completed}/${TICKS}"
  exit 0
fi

write_result_json "true" "COMPLETED" "$summary_json"
echo "OMEGA_WEEKEND: COMPLETE pass=true reason=COMPLETED ticks=${ticks_completed}/${TICKS}"
exit 0
