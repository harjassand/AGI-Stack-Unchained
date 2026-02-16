#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <EPOCH_ID> <OUT_DIR> <STATE_DIR>" >&2
  exit 2
fi

EPOCH_ID="$1"
OUT_DIR="$2"
STATE_DIR="$3"

if [[ -z "${CDEL_SEALED_PRIVKEY:-}" ]]; then
  echo "CDEL_SEALED_PRIVKEY must be set in the environment" >&2
  exit 2
fi

STATE_DIR_REAL="$(cd "$STATE_DIR" && pwd)"
RUN_INSTANCE="$(cd "$STATE_DIR_REAL/.." && pwd)"
RUN_ROOT="$(cd "$RUN_INSTANCE/.." && pwd)"

BASE_ONTOLOGY="$STATE_DIR_REAL/current/base_ontology.json"
BASE_MECH="$STATE_DIR_REAL/current/base_mech.json"
SUITEPACK_DEV="$RUN_ROOT/suitepacks/dev/suitepack.json"
SUITEPACK_HELDOUT="$RUN_ROOT/suitepacks/heldout/suitepack.json"
HELDOUT_SUITE_ID="caoe_switchboard_heldout_v1"
CDEL_BIN="$RUN_INSTANCE/cdel_shim"
MAX_CANDIDATES="${MAX_CANDIDATES:-16}"
DEV_ORACLE_SEQUENCE="${DEV_ORACLE_SEQUENCE:-}"
DEV_ORACLE_MEMORYLESS="${DEV_ORACLE_MEMORYLESS:-}"
DEV_ORACLE_DEPTH2="${DEV_ORACLE_DEPTH2:-}"

if [[ ! -f "$BASE_ONTOLOGY" ]] || [[ ! -f "$BASE_MECH" ]]; then
  echo "base ontology/mech not found under $STATE_DIR_REAL/current" >&2
  exit 2
fi
if [[ ! -f "$SUITEPACK_DEV" ]] || [[ ! -f "$SUITEPACK_HELDOUT" ]]; then
  echo "suitepacks not found under $RUN_ROOT/suitepacks" >&2
  exit 2
fi
if [[ ! -x "$CDEL_BIN" ]]; then
  echo "cdel shim not executable at $CDEL_BIN" >&2
  exit 2
fi

if [[ -z "${META_CORE_ROOT:-}" ]]; then
  META_CORE_ROOT="$RUN_ROOT/meta_core_root"
  export META_CORE_ROOT
fi

mkdir -p "$OUT_DIR"

RUN_CMD=(
  python3 Extension-1/caoe_v1/cli/caoe_proposer_cli_v1.py run-epoch
  --epoch_id "$EPOCH_ID"
  --base_ontology "$BASE_ONTOLOGY"
  --base_mech "$BASE_MECH"
  --suitepack_dev "$SUITEPACK_DEV"
  --suitepack_heldout "$SUITEPACK_HELDOUT"
  --heldout_suite_id "$HELDOUT_SUITE_ID"
  --cdel_bin "$CDEL_BIN"
  --state_dir "$STATE_DIR_REAL"
  --out_dir "$OUT_DIR"
  --max_candidates "$MAX_CANDIDATES"
  --eval_plan full
  --workers 1
)

if [[ -n "$DEV_ORACLE_SEQUENCE" ]]; then
  RUN_CMD+=(--dev_oracle_sequence "$DEV_ORACLE_SEQUENCE")
fi
if [[ -n "$DEV_ORACLE_MEMORYLESS" ]]; then
  RUN_CMD+=(--dev_oracle_memoryless "$DEV_ORACLE_MEMORYLESS")
fi
if [[ -n "$DEV_ORACLE_DEPTH2" ]]; then
  RUN_CMD+=(--dev_oracle_depth2 "$DEV_ORACLE_DEPTH2")
fi

{
  echo "CDEL_SEALED_PRIVKEY=<REDACTED>"
  echo "META_CORE_ROOT=$META_CORE_ROOT"
  printf "%q " "${RUN_CMD[@]}"
  echo
} > "$OUT_DIR/run_command_redacted.txt"

"${RUN_CMD[@]}"
