#!/usr/bin/env bash
set -u -o pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

CAMPAIGN_PACK="campaigns/rsi_omega_daemon_v19_0_super_unified/rsi_omega_daemon_pack_v1.json"
START_TICK="${OMEGA_IGNITE_START_TICK:-1}"
OUT_ROOT="${OMEGA_IGNITE_OUT_ROOT:-runs/ignite_v19_super_unified}"
LOG_PATH="${OMEGA_IGNITE_LOG_PATH:-runaway_evolution.log}"
SLEEP_SECONDS="${OMEGA_IGNITE_SLEEP_SECONDS:-1}"
ACTIVATION_MODE="${OMEGA_META_CORE_ACTIVATION_MODE:-simulate}"
ALLOW_SIMULATE="${OMEGA_ALLOW_SIMULATE_ACTIVATION:-1}"

if ! [[ "$START_TICK" =~ ^[0-9]+$ ]]; then
  echo "OMEGA_IGNITE_START_TICK must be an unsigned integer" >&2
  exit 2
fi
if ! [[ "$SLEEP_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "OMEGA_IGNITE_SLEEP_SECONDS must be numeric" >&2
  exit 2
fi

RAW_ROOT="${OUT_ROOT}/raw"
mkdir -p "$RAW_ROOT"
mkdir -p "$(dirname "$LOG_PATH")"

timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_line() {
  local payload="$1"
  printf '%s %s\n' "$(timestamp_utc)" "$payload" | tee -a "$LOG_PATH"
}

emit_signals_for_tick() {
  local tick_u64="$1"
  local state_dir="$2"
  local raw_log="$3"

  python3 - "$tick_u64" "$state_dir" "$raw_log" <<'PY'
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

tick_u64 = int(sys.argv[1])
state_dir = Path(sys.argv[2])
raw_log = Path(sys.argv[3])


def latest(pattern: str) -> Path | None:
    rows = sorted(glob.glob(pattern))
    if not rows:
        return None
    return Path(rows[-1])


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def as_token(value: Any) -> str:
    text = str(value)
    if text == "":
        return "NA"
    text = re.sub(r"\s+", "_", text.strip())
    return text if text else "NA"


def hash_from_filename(path: Path | None, suffix: str) -> str:
    if path is None:
        return ""
    name = path.name
    if name.startswith("sha256_") and name.endswith(suffix):
        digest = name[len("sha256_") : -len(suffix)]
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return f"sha256:{digest}"
    return ""


def emit(signal: str, **fields: Any) -> None:
    parts = [f"SIGNAL={signal}", f"tick={tick_u64}"]
    for key, value in fields.items():
        parts.append(f"{key}={as_token(value)}")
    print(" ".join(parts))


runaway_state = ""
runaway_level = -1
runaway_reason = ""
action_kind_cli = ""
decision_plan_hash_cli = ""
trace_hash_chain_hash_cli = ""
tick_snapshot_hash_cli = ""

if raw_log.exists():
    for raw in raw_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("runaway_state:"):
            runaway_state = line.split(":", 1)[1].strip()
        elif line.startswith("runaway_level_u64:"):
            val = line.split(":", 1)[1].strip()
            try:
                runaway_level = int(val)
            except Exception:
                runaway_level = -1
        elif line.startswith("runaway_reason:"):
            runaway_reason = line.split(":", 1)[1].strip()
        elif line.startswith("action_kind:"):
            action_kind_cli = line.split(":", 1)[1].strip()
        elif line.startswith("decision_plan_hash:"):
            decision_plan_hash_cli = line.split(":", 1)[1].strip()
        elif line.startswith("trace_hash_chain_hash:"):
            trace_hash_chain_hash_cli = line.split(":", 1)[1].strip()
        elif line.startswith("tick_snapshot_hash:"):
            tick_snapshot_hash_cli = line.split(":", 1)[1].strip()

decision_path = latest(str(state_dir / "decisions" / "sha256_*.omega_decision_plan_v1.json"))
decision = load_json(decision_path) or {}
decision_plan_hash = decision_plan_hash_cli or hash_from_filename(decision_path, ".omega_decision_plan_v1.json")

tick_outcome_path = latest(str(state_dir / "perf" / "sha256_*.omega_tick_outcome_v1.json"))
tick_outcome = load_json(tick_outcome_path) or {}
trace_hash_chain_hash = trace_hash_chain_hash_cli or str(tick_outcome.get("trace_hash_chain_hash", "")).strip()
tick_snapshot_hash = tick_snapshot_hash_cli or str(tick_outcome.get("tick_snapshot_hash", "")).strip()

promotion_path = latest(str(state_dir / "dispatch" / "*" / "promotion" / "sha256_*.omega_promotion_receipt_v1.json"))
promotion = load_json(promotion_path) or {}
promotion_status = str((promotion.get("result") or {}).get("status", "")).strip()

activation_path = latest(str(state_dir / "dispatch" / "*" / "activation" / "sha256_*.omega_activation_receipt_v1.json"))
activation = load_json(activation_path) or {}
activation_success = bool(activation.get("activation_success", False))

ccap_path = latest(str(state_dir / "dispatch" / "*" / "verifier" / "sha256_*.ccap_receipt_v1.json"))
ccap = load_json(ccap_path) or {}
ccap_decision = str(ccap.get("decision", "")).strip()

rewrite_bundle_paths = sorted(glob.glob(str(state_dir / "subruns" / "*" / "promotion" / "sha256_*.omega_promotion_bundle_ccap_v1.json")))
rewrite_attempt = bool(rewrite_bundle_paths)
rewrite_bundle_rel = ""
if rewrite_bundle_paths:
    try:
        rewrite_bundle_rel = os.path.relpath(rewrite_bundle_paths[-1], state_dir)
    except Exception:
        rewrite_bundle_rel = rewrite_bundle_paths[-1]

selected_metric = str(decision.get("runaway_selected_metric_id", "")).strip()
selected_level = int(decision.get("runaway_escalation_level_u64", -1) or -1)
campaign_id = str(decision.get("campaign_id", "")).strip()
tie_break_path = decision.get("tie_break_path")
if not isinstance(tie_break_path, list):
    tie_break_path = []
tie_break_has_reason = any(str(row).strip() == "RUNAWAY_REASON:TESTING" for row in tie_break_path)

runaway_active = runaway_state == "ACTIVE" and runaway_level == 5 and runaway_reason == "TESTING"
capability_priority = (
    selected_metric == "OBJ_EXPAND_CAPABILITIES"
    and selected_level == 5
    and campaign_id == "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    and tie_break_has_reason
)
rewrite_commit = promotion_status == "PROMOTED"
manifest_changed = bool(tick_outcome.get("manifest_changed", False))
activation_commit = activation_success and manifest_changed

if runaway_active:
    emit("RUNAWAY_ACTIVE", level=runaway_level, reason=runaway_reason)

if capability_priority:
    emit(
        "CAPABILITY_PRIORITY",
        metric=selected_metric,
        campaign=campaign_id,
        level=selected_level,
        reason_trace="RUNAWAY_REASON:TESTING",
    )

if rewrite_attempt:
    emit(
        "REWRITE_ATTEMPT",
        bundle="omega_promotion_bundle_ccap_v1",
        bundle_rel=rewrite_bundle_rel,
    )

if ccap_decision in {"PROMOTE", "REJECT"}:
    emit(
        "CCAP_DECISION",
        decision=ccap_decision,
        ccap_id=str(ccap.get("ccap_id", "")),
    )

if rewrite_commit:
    emit(
        "REWRITE_COMMIT",
        promotion_status=promotion_status,
        receipt=hash_from_filename(promotion_path, ".omega_promotion_receipt_v1.json"),
    )

if activation_commit:
    emit(
        "ACTIVATION_COMMIT",
        activation_success=str(activation_success).lower(),
        manifest_changed=str(manifest_changed).lower(),
        receipt=hash_from_filename(activation_path, ".omega_activation_receipt_v1.json"),
    )

action_kind = str(decision.get("action_kind", "")).strip() or action_kind_cli
emit(
    "HEARTBEAT",
    action_kind=action_kind,
    decision_plan_hash=decision_plan_hash,
    trace_hash_chain_hash=trace_hash_chain_hash,
    tick_snapshot_hash=tick_snapshot_hash,
)

emit(
    "TIER_STATUS",
    tier1=("pass" if (runaway_active and capability_priority) else "fail"),
    tier2=("pass" if rewrite_attempt else "fail"),
    tier3=("pass" if (rewrite_commit and activation_commit) else "fail"),
    selected_metric=selected_metric,
    promotion_status=(promotion_status or "NONE"),
    activation_success=str(activation_success).lower(),
    manifest_changed=str(manifest_changed).lower(),
)
PY
}

tick_u64="$START_TICK"
prev_state_dir=""
consecutive_crash_count=0
attempt_u64=0

log_line "SIGNAL=IGNITE_START tick=${tick_u64} profile=rsi_omega_daemon_v19_0_super_unified campaign_pack=${CAMPAIGN_PACK}"

trap 'log_line "SIGNAL=IGNITE_STOP tick=${tick_u64} reason=INTERRUPTED"; exit 0' INT TERM

while :; do
  tick_id="$(printf '%04d' "$tick_u64")"
  out_dir="${OUT_ROOT}_tick_${tick_id}"

  attempt_u64=$((attempt_u64 + 1))
  attempt_id="$(printf '%04d' "$attempt_u64")"
  raw_log="${RAW_ROOT}/tick_${tick_id}_attempt_${attempt_id}.log"
  rm -rf "$out_dir"

  cmd=(
    python3 -m orchestrator.rsi_omega_daemon_v19_0
    --campaign_pack "$CAMPAIGN_PACK"
    --out_dir "$out_dir"
    --mode once
    --tick_u64 "$tick_u64"
  )
  if [[ -n "$prev_state_dir" ]]; then
    cmd+=(--prev_state_dir "$prev_state_dir")
  fi

  env \
    PYTHONPATH=".:CDEL-v2:Extension-1/agi-orchestrator${PYTHONPATH:+:${PYTHONPATH}}" \
    OMEGA_META_CORE_ACTIVATION_MODE="$ACTIVATION_MODE" \
    OMEGA_ALLOW_SIMULATE_ACTIVATION="$ALLOW_SIMULATE" \
    "${cmd[@]}" >"$raw_log" 2>&1
  run_status="$?"

  if [[ "$run_status" == "0" ]]; then
    state_dir="${out_dir}/daemon/rsi_omega_daemon_v19_0/state"
    if [[ ! -d "$state_dir" ]]; then
      consecutive_crash_count=$((consecutive_crash_count + 1))
      log_line \
        "SIGNAL=RESURRECT tick=${tick_u64} exit_code=MISSING_STATE_DIR consecutive_crash_count=${consecutive_crash_count} raw_log=${raw_log}"
      sleep "$SLEEP_SECONDS"
      continue
    fi

    while IFS= read -r row; do
      [[ -n "$row" ]] || continue
      log_line "$row"
    done < <(emit_signals_for_tick "$tick_u64" "$state_dir" "$raw_log")

    prev_state_dir="$state_dir"
    tick_u64=$((tick_u64 + 1))
    consecutive_crash_count=0
    attempt_u64=0
    continue
  fi

  exit_code="$run_status"
  consecutive_crash_count=$((consecutive_crash_count + 1))
  log_line \
    "SIGNAL=RESURRECT tick=${tick_u64} exit_code=${exit_code} consecutive_crash_count=${consecutive_crash_count} raw_log=${raw_log}"
  sleep "$SLEEP_SECONDS"
done
