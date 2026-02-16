#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

T="${1:-30}"
PACK="campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json"
PREFIX="rsi_omega_daemon_v18_0_prod_tick_"

OMEGA_PACK="$PACK" OMEGA_RUN_PREFIX="$PREFIX" scripts/run_omega_ticks_v18_0.sh "$T"

summary="$(OMEGA_WEEKEND_T="$T" PYTHONPATH="CDEL-v2:." python3 - <<'PY'
import json
import os
from pathlib import Path

prefix = "rsi_omega_daemon_v18_0_prod_tick_"
runs = []
for tick in range(1, int(os.environ["OMEGA_WEEKEND_T"]) + 1):
    row = Path("runs") / f"{prefix}{tick:04d}"
    if row.is_dir():
        runs.append(row)
if not runs:
    print("OMEGA_WEEKEND: VALID ticks=0 goals_done=0 promotions=0 activations=0 best_metric_delta_q32=0")
    raise SystemExit(0)

promotions = 0
activations = 0
Q32_ONE = 1 << 32
best_delta = 0

for run in runs:
    state = run / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    for pf in sorted(state.glob("dispatch/*/promotion/sha256_*.meta_core_promo_verify_receipt_v1.json")):
        obj = json.loads(pf.read_text(encoding="utf-8"))
        if bool(obj.get("pass")):
            promotions += 1
    for af in sorted(state.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json")):
        obj = json.loads(af.read_text(encoding="utf-8"))
        if bool(obj.get("activation_success")):
            activations += 1

    for report_path in sorted(run.glob("**/*.metasearch_compute_report_v1.json")):
        obj = json.loads(report_path.read_text(encoding="utf-8"))
        c_base = obj.get("c_base_work_cost_total")
        c_cand = obj.get("c_cand_work_cost_total")
        if not isinstance(c_base, int) or not isinstance(c_cand, int):
            continue
        if c_base <= 0 or c_cand < 0:
            continue
        delta_q = ((c_base - c_cand) * Q32_ONE) // c_base
        if delta_q > best_delta:
            best_delta = delta_q

latest_state_dir = runs[-1] / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "state"
state_files = sorted(latest_state_dir.glob("sha256_*.omega_state_v1.json"))
goals_done = 0
if state_files:
    state_obj = json.loads(state_files[-1].read_text(encoding="utf-8"))
    goals = state_obj.get("goals")
    if isinstance(goals, dict):
        goals_done = sum(1 for row in goals.values() if isinstance(row, dict) and row.get("status") == "DONE")

print(
    "OMEGA_WEEKEND: VALID "
    f"ticks={len(runs)} "
    f"goals_done={goals_done} "
    f"promotions={promotions} "
    f"activations={activations} "
    f"best_metric_delta_q32={best_delta}"
)
PY
)"

echo "$summary"
