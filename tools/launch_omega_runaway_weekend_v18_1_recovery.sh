#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TICKS=100
CAMPAIGN_PACK="campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json"
OUT_ROOT="runs/rsi_omega_runaway_v18_1"
MAX_RESTARTS=2
RETRY_SLEEP_SECONDS=20
LOG_PATH=""

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
    --max_restarts)
      MAX_RESTARTS="$2"
      shift 2
      ;;
    --retry_sleep_seconds)
      RETRY_SLEEP_SECONDS="$2"
      shift 2
      ;;
    --log_path)
      LOG_PATH="$2"
      shift 2
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if ! [[ "$MAX_RESTARTS" =~ ^[0-9]+$ ]]; then
  echo "invalid --max_restarts: $MAX_RESTARTS" >&2
  exit 2
fi
if ! [[ "$RETRY_SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "invalid --retry_sleep_seconds: $RETRY_SLEEP_SECONDS" >&2
  exit 2
fi

if [[ -z "$LOG_PATH" ]]; then
  ts="$(date -u +%Y%m%d_%H%M%S)"
  log_name="$(basename "$OUT_ROOT")_${ts}.recovery.log"
  LOG_PATH="runs/logs/${log_name}"
fi
mkdir -p "$(dirname "$LOG_PATH")"

attempt=1
max_attempts=$((MAX_RESTARTS + 1))
while (( attempt <= max_attempts )); do
  {
    echo "START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ) attempt=${attempt}/${max_attempts}"
    echo "CMD=bash scripts/run_omega_runaway_weekend_v18_1.sh --ticks ${TICKS} --campaign_pack ${CAMPAIGN_PACK} --out_root ${OUT_ROOT}"
  } >>"$LOG_PATH"

  if bash scripts/run_omega_runaway_weekend_v18_1.sh \
    --ticks "$TICKS" \
    --campaign_pack "$CAMPAIGN_PACK" \
    --out_root "$OUT_ROOT" >>"$LOG_PATH" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if (( rc == 0 )); then
    {
      echo "END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ) status=SUCCESS attempt=${attempt}/${max_attempts}"
      echo "LOG_PATH=$LOG_PATH"
    } >>"$LOG_PATH"
    echo "SUCCESS log=$LOG_PATH"
    exit 0
  fi
  {
    echo "END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ) status=FAIL exit_code=${rc} attempt=${attempt}/${max_attempts}"
  } >>"$LOG_PATH"

  if (( attempt >= max_attempts )); then
    echo "FAIL exit_code=${rc} log=$LOG_PATH" >&2
    exit "$rc"
  fi

  sleep "$RETRY_SLEEP_SECONDS"
  attempt=$((attempt + 1))
done
