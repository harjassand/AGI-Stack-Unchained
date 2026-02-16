#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

T=45
PACK="campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json"
PREFIX="rsi_omega_daemon_v18_0_prod_tick_"

if [[ "${OMEGA_RESET_ACTIVE_BASELINE:-1}" == "1" ]]; then
  META_CORE_ROOT="${OMEGA_META_CORE_ROOT:-meta-core}"
  baseline_hex="$(python3 - "$META_CORE_ROOT" <<'PY'
import sys
from pathlib import Path

meta_core_root = Path(sys.argv[1])
store = meta_core_root / "store" / "bundles"
if not store.exists() or not store.is_dir():
    print("")
    raise SystemExit(0)

candidate = ""
for row in sorted(store.glob("*")):
    if not row.is_dir():
        continue
    if not (row / "constitution.manifest.json").exists():
        continue
    if (row / "omega" / "omega_activation_binding_v1.json").exists():
        continue
    candidate = row.name
    break
print(candidate)
PY
)"
  if [[ -n "$baseline_hex" ]]; then
    printf '%s\n' "$baseline_hex" > "${META_CORE_ROOT}/active/ACTIVE_BUNDLE"
    printf '%s\n' "$baseline_hex" > "${META_CORE_ROOT}/active/PREV_ACTIVE_BUNDLE"
  fi
fi

OMEGA_PACK="$PACK" OMEGA_RUN_PREFIX="$PREFIX" OMEGA_LIGHTWEIGHT_SUBVERIFIER="${OMEGA_LIGHTWEIGHT_SUBVERIFIER:-0}" scripts/run_omega_ticks_v18_0.sh "$T"

summary="$(OMEGA_DEMO_T="$T" OMEGA_DEMO_PREFIX="$PREFIX" PYTHONPATH="CDEL-v2:." python3 - <<'PY'
import json
import os
from pathlib import Path

ticks_target = int(os.environ["OMEGA_DEMO_T"])
prefix = os.environ["OMEGA_DEMO_PREFIX"]
runs = []
for tick in range(1, ticks_target + 1):
    row = Path("runs") / f"{prefix}{tick:04d}"
    if row.is_dir():
        runs.append(row)
if not runs:
    print("OMEGA_DEMO: VALID ticks=0 promotions=0 best_metric_delta_q32=0")
    raise SystemExit(0)

promotions = 0
activations = 0
manifest_changes = 0
activation_caps: list[str] = []
goals_done_tick = None
post_goal_all_noop = True
Q32_ONE = 1 << 32
for run in runs:
    state = run / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    decision_files = sorted(state.glob("decisions/sha256_*.omega_decision_plan_v1.json"))
    action_kind = "MISSING"
    assigned_cap = None
    if decision_files:
        decision = json.loads(decision_files[-1].read_text(encoding="utf-8"))
        action_kind = decision.get("action_kind", "MISSING")
        assigned_cap = decision.get("assigned_capability_id") or decision.get("capability_id")

    promo_files = sorted(state.glob("dispatch/*/promotion/sha256_*.meta_core_promo_verify_receipt_v1.json"))
    for pf in promo_files:
        obj = json.loads(pf.read_text(encoding="utf-8"))
        if bool(obj.get("pass")):
            promotions += 1
    activation_files = sorted(state.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json"))
    for af in activation_files:
        obj = json.loads(af.read_text(encoding="utf-8"))
        if bool(obj.get("activation_success")):
            activations += 1
            if isinstance(assigned_cap, str):
                activation_caps.append(assigned_cap)
        if obj.get("before_active_manifest_hash") != obj.get("after_active_manifest_hash"):
            manifest_changes += 1

    state_rows = sorted((state / "state").glob("sha256_*.omega_state_v1.json"))
    if state_rows:
        state_obj = json.loads(state_rows[-1].read_text(encoding="utf-8"))
        goals = state_obj.get("goals")
        if isinstance(goals, dict) and goals and all(
            isinstance(row, dict) and row.get("status") == "DONE" for row in goals.values()
        ):
            if goals_done_tick is None:
                goals_done_tick = int(run.name.split("_")[-1])
        if goals_done_tick is not None and int(run.name.split("_")[-1]) > goals_done_tick and action_kind != "NOOP":
            post_goal_all_noop = False

best_delta = 0
for report_path in sorted(Path("runs").glob(f"{prefix}*/**/*.metasearch_compute_report_v1.json")):
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

required_caps = {
    "RSI_SAS_CODE",
    "RSI_SAS_METASEARCH",
    "RSI_SAS_VAL",
    "RSI_SAS_SCIENCE",
    "RSI_SAS_SYSTEM",
    "RSI_SAS_KERNEL",
}
if len(runs) != ticks_target:
    raise SystemExit(f"OMEGA_DEMO_ASSERT_FAIL:ticks={len(runs)} expected={ticks_target}")
if promotions != 6:
    raise SystemExit(f"OMEGA_DEMO_ASSERT_FAIL:promotions={promotions} expected=6")
if activations != 6:
    raise SystemExit(f"OMEGA_DEMO_ASSERT_FAIL:activations={activations} expected=6")
if manifest_changes != activations:
    raise SystemExit(
        f"OMEGA_DEMO_ASSERT_FAIL:active_manifest_changes={manifest_changes} activations={activations}"
    )
if set(activation_caps) != required_caps:
    raise SystemExit(
        f"OMEGA_DEMO_ASSERT_FAIL:activation_caps={sorted(set(activation_caps))} expected={sorted(required_caps)}"
    )
if not post_goal_all_noop:
    raise SystemExit("OMEGA_DEMO_ASSERT_FAIL:post_goal_actions_not_noop")

print(
    "OMEGA_DEMO: VALID "
    f"ticks={len(runs)} "
    f"promotions={promotions} "
    f"activations={activations} "
    f"active_manifest_changes={manifest_changes} "
    f"best_metric_delta_q32={best_delta}"
)
PY
)"

echo "$summary"
