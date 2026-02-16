#!/usr/bin/env bash
set -euo pipefail

# Phase-5 plan closure runner (deterministic, no absolute paths)

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SPEC_ROOT="$SCRIPT_DIR"
if [[ -x "$SCRIPT_DIR/tools/find_repo_root.py" ]]; then
  SPEC_ROOT=$(python3 "$SCRIPT_DIR/tools/find_repo_root.py" --start "$SCRIPT_DIR" --key specpack_root 2>/dev/null || true)
fi
SPEC_ROOT=${SPEC_ROOT:-"$SCRIPT_DIR"}

GENESIS_ROOT=${GENESIS_ROOT:-"$SPEC_ROOT/genesis"}
CDEL_ROOT=${CDEL_ROOT:-"$SPEC_ROOT/cdel"}
REPORT_PATH=${REPORT_PATH:-"$SPEC_ROOT/PLAN_CLOSURE_VERIFICATION.txt"}
REDTEAM_REPORT=${REDTEAM_REPORT:-"$SPEC_ROOT/GENESIS_REDTEAM_REPORT.json"}
HARDENING_LEDGER_DIR=${HARDENING_LEDGER_DIR:-"$CDEL_ROOT/.cdel_ledger_hardening"}
HARDENING_REPORT=${HARDENING_REPORT:-"$SPEC_ROOT/HARDFIX_REPORT.json"}

if [[ ! -d "$GENESIS_ROOT" ]]; then
  echo "GENESIS_ROOT not found: $GENESIS_ROOT" >&2
  exit 2
fi
if [[ ! -d "$CDEL_ROOT" ]]; then
  echo "CDEL_ROOT not found: $CDEL_ROOT" >&2
  exit 2
fi

python3 "$GENESIS_ROOT/tools/verify_specpack_lock.py"
python3 "$CDEL_ROOT/specpack_verify_lock.py"

# ALGORITHM
CDEL_ROOT="$CDEL_ROOT" bash "$GENESIS_ROOT/run_end_to_end.sh"

# WORLD_MODEL
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v0_4.py" --config "$GENESIS_ROOT/configs/world_model.json"

# POLICY
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v0_5.py" \
  --world-model-config "$GENESIS_ROOT/configs/world_model.json" \
  --policy-config "$GENESIS_ROOT/configs/policy.json"

# CAUSAL_MODEL
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v1_3.py" \
  --causal-config "$GENESIS_ROOT/configs/causal_v1_3.json"

# SYSTEM + release pack with eval bundle
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v1_2.py" \
  --system-config "$GENESIS_ROOT/configs/system_v1_2.json"

# CDEL hardening suite
python3 "$CDEL_ROOT/tools/hardening/run_hardening_suite.py" \
  --ledger-dir "$HARDENING_LEDGER_DIR" \
  --report "$HARDENING_REPORT"

# Genesis red-team runner (local refusals, no CDEL calls)
python3 "$GENESIS_ROOT/tools/redteam_genesis.py" --out "$REDTEAM_REPORT"

cat <<'REPORT' > "$REPORT_PATH"
Commands:
python3 "$GENESIS_ROOT/tools/verify_specpack_lock.py"
python3 "$CDEL_ROOT/specpack_verify_lock.py"
CDEL_ROOT="$CDEL_ROOT" bash "$GENESIS_ROOT/run_end_to_end.sh"
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v0_4.py" --config "$GENESIS_ROOT/configs/world_model.json"
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v0_5.py" --world-model-config "$GENESIS_ROOT/configs/world_model.json" --policy-config "$GENESIS_ROOT/configs/policy.json"
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v1_3.py" --causal-config "$GENESIS_ROOT/configs/causal_v1_3.json"
CDEL_ROOT="$CDEL_ROOT" python3 "$GENESIS_ROOT/run_end_to_end_v1_2.py" --system-config "$GENESIS_ROOT/configs/system_v1_2.json"
python3 "$CDEL_ROOT/tools/hardening/run_hardening_suite.py" --ledger-dir "$HARDENING_LEDGER_DIR" --report "$HARDENING_REPORT"
python3 "$GENESIS_ROOT/tools/redteam_genesis.py" --out "$REDTEAM_REPORT"

Outcome:
- Specpack lock verified.
- One PASS promotion executed for ALGORITHM, WORLD_MODEL, POLICY, CAUSAL_MODEL, SYSTEM.
- SYSTEM release pack with eval bundle produced and verified.
- CDEL hardening suite PASS.
- Genesis red-team PASS (local refusals; no CDEL calls).
REPORT
