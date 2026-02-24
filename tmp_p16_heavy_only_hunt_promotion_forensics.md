# P16 Heavy-Only Hunt Promotion Forensics (Thorough)

Generated (UTC): 2026-02-24 00:04:13Z

## Scope

- Target run: `runs/p16_repin_heavy_only_hunt_fast_v1`
- Goal: document exactly what got promoted, how it got promoted, and the exact patch/fdiff used.

---

## 1) Final Outcome (Ground Truth)

The run achieved heavy promotion and stopped at tick 4.

- Stop receipt: `runs/p16_repin_heavy_only_hunt_fast_v1/LONG_RUN_STOP_RECEIPT_v1.json`
- `halt_reason_code`: `HEAVY_PROMOTED`
- `halt_tick_u64`: `4`
- `detail.ccap_decision`: `PROMOTE`
- `state_verifier_reason_code`: `null`

File hash:

- `LONG_RUN_STOP_RECEIPT_v1.json` -> `sha256:8a6a718fe85815302f8266dd7cf0875cfd010607555d052ea498c4c3bda5ed49`

---

## 2) What Got Promoted

### 2.1 Promoted capability and tick

From `runs/p16_repin_heavy_only_hunt_fast_v1/index/long_run_tick_index_v1.jsonl`:

- Promoted heavy tick: `tick_u64=4`
- `selected_capability_id=RSI_GE_SH1_OPTIMIZER`
- `action_kind=RUN_GOAL_TASK`
- `declared_class=FRONTIER_HEAVY`
- `effect_class=EFFECT_HEAVY_OK`
- `heavy_utility_ok_b=true`
- `heavy_promoted_b=true`
- `ccap_eval_status=PASS`
- `ccap_decision=PROMOTE`
- `ccap_smoke_rung_u8=2`
- `hard_stop_reason_code=HEAVY_PROMOTED`

### 2.2 Tick timeline (ticks 1-4)

- Tick 1: maintenance promotion (`PROMOTE`), `heavy_utility_ok_b=false`.
- Tick 2: maintenance promotion (`PROMOTE`), `heavy_utility_ok_b=false`.
- Tick 3: maintenance promotion (`PROMOTE`), `heavy_utility_ok_b=false`.
- Tick 4: forced frontier heavy attempt, heavy utility success, promoted, run halted.

All 4 ticks used smoke rung 2 (`ccap_smoke_rung_u8=2`).

File hash:

- `index/long_run_tick_index_v1.jsonl` -> `sha256:bf99f9679416292dffc7028fb9249bb79bc7f638233bae112c603cfb212a0134`

---

## 3) Run Configuration That Produced the Promotion

Launch manifest:
`runs/p16_repin_heavy_only_hunt_fast_v1/configs/long_run_launch_manifest_v1.json`

Key env/control settings:

- `OMEGA_CCAP_SMOKE_EK_B=1`
- `OMEGA_CCAP_SMOKE_ONLY_B=1`
- `OMEGA_CCAP_SMOKE_SCORE_TICKS_U64=5`
- `OMEGA_CCAP_SMOKE_BUDGET_START_RUNG_U8=1`
- `OMEGA_CCAP_SMOKE_BUDGET_MAX_BUMPS_U8=1`
- `OMEGA_CCAP_SMOKE_BUDGET_LADDER_V1=[[60000,60000,1024,536870912],[300000,120000,4096,2147483648],[420000,240000,6144,3221225472]]`
- `OMEGA_CCAP_SMOKE_WINNER_ESCALATE_FULL_EK_B=0`
- `OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B=1`
- `OMEGA_MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64=40`
- `execution.max_ticks=40`

Runtime provenance:

- `resolved_orch_llm_backend=mlx`
- `resolved_orch_model_id=mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`

---

## 4) How It Got Promoted (Step-by-Step Evidence Chain)

### Step A: Mission and frontier routing forced a heavy attempt

Mission ingest receipt:
`.../state/long_run/mission/sha256_8def6f...mission_goal_ingest_receipt_v1.json`

- `goal_id=goal_auto_10_mission_rsi_ge_sh1_optimizer_000004_01`
- `status=MISSION_GOAL_ADDED`

Dependency routing receipt:
`.../state/long_run/debt/sha256_09eba1...dependency_routing_receipt_v1.json`

- `routing_selector_id=HARD_LOCK_OVERRIDE`
- `selected_capability_id=RSI_GE_SH1_OPTIMIZER`
- `selected_declared_class=FRONTIER_HEAVY`
- `forced_frontier_attempt_b=true`
- reason codes:
  - `DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT`
  - `FORCED_FRONTIER_ATTEMPT_NOT_ELIGIBLE`
  - `FORCED_TARGETED_FRONTIER_ATTEMPT`
  - `MILESTONE_FORCE_SH1_FRONTIER`

Debt state receipt:
`.../state/long_run/debt/sha256_bff538...dependency_debt_state_v1.json`

- `reason_code=FRONTIER_ATTEMPT_COUNTED`
- `frontier_attempts_u64=1`
- `heavy_ok_count_by_capability.RSI_GE_SH1_OPTIMIZER=1`

### Step B: Decision plan selected forced frontier goal path

Decision plan:
`.../state/decisions/sha256_9002c2....omega_decision_plan_v1.json`

- `action_kind=RUN_GOAL_TASK`
- `assigned_capability_id=RSI_GE_SH1_OPTIMIZER`
- `goal_id=goal_auto_10_mission_rsi_ge_sh1_optimizer_000004_01`
- `tie_break_path` includes:
  - `POLICY_VM_V1`
  - `FORCED_FRONTIER_GOAL:goal_auto_10_mission_rsi_ge_sh1_optimizer_000004_01`
  - `FORCED_FRONTIER_OVERRIDE`

### Step C: Dispatch executed with forced-heavy SH1 overrides

Dispatch receipt:
`.../state/dispatch/1da7bba6fb8d81c6/sha256_02b28efa....omega_dispatch_receipt_v1.json`

- `dispatch_attempted_b=true`
- `return_code=0`
- env overrides applied:
  - `OMEGA_SH1_FORCED_DEBT_KEY=frontier:rsi_ge_sh1_optimizer`
  - `OMEGA_SH1_FORCED_HEAVY_B=1`
  - `OMEGA_SH1_WIRING_LOCUS_RELPATH=orchestrator/omega_v18_0/goal_synthesizer_v1.py`

### Step D: CCAP evaluation passed and promoted candidate

CCAP receipt:
`.../state/dispatch/1da7bba6fb8d81c6/verifier/sha256_38094791....ccap_receipt_v1.json`

- `eval_status=PASS`
- `decision=PROMOTE`
- `determinism_check=PASS`
- `smoke_rung_u8=2`
- `ccap_id=sha256:7e8625e314f05eaaa2ca28743ec7915113a4c338f82dddb5300fda2ca8496c81`
- `base_tree_id=sha256:4270c8cbd99e12cc49b28458c76d4c09b358c54d431cf035362a07604bc873ab`
- `applied_tree_id=sha256:1592404e304f905b42849312b4a7c6d060bd98778dd939fde5a2ca78261bbc10`

Cost vector:

- `wall_ms=285133`
- `cpu_ms=15684`
- `disk_mb=3634`
- `mem_mb=633`
- `fds=4`

Effective tuple in receipt:

- `time_ms_max=600000`
- `stage_cost_budget=600000`
- `disk_mb_max=8192`
- `artifact_bytes_max=8589934592`

### Step E: Utility proof marked heavy path as valid

Utility proof receipt:
`.../state/dispatch/1da7bba6fb8d81c6/promotion/sha256_ba944451....utility_proof_receipt_v1.json`

- `declared_class=FRONTIER_HEAVY`
- `effect_class=EFFECT_HEAVY_OK`
- `reason_code=UTILITY_OK`
- `utility_ok_b=true`
- `correctness_ok_b=true`
- `signal_a_ok_b=true`
- `signal_b_ok_b=true`
- `probe_executed_b=true`

Hard-task / utility deltas (selected):

- `hard_task_any_gain_b=true`
- `hard_task_baseline_init_b=false`
- `hard_task_delta_q32=3435973837`
- `predicted_hard_task_delta_q32=3435973837`
- `non_ws_non_comment_delta_u64=9`
- `j_delta_q32_i64=3435973837`

Threshold contract in receipt:

- `primary_signal=NONTRIVIAL_DELTA`
- `primary_threshold_u64=1`
- `stress_signal=REQUIRE_PATCH_DELTA`
- `stress_threshold_u64=1`
- `require_hard_task_gain_b=true`

### Step F: Subverifiers and governance checks passed

Subverifier receipt (nontriviality-rich):
`.../verifier/sha256_b3345fe2....omega_subverifier_receipt_v1.json`

- `result.status=VALID`
- `verifier_module=cdel.v18_0.verify_ccap_v1`
- `nontriviality_cert_v1.patch_parse_ok_b=true`
- `nontriviality_cert_v1.ast_parse_ok_b=true`
- `nontriviality_cert_v1.wiring_class_ok_b=true`
- `nontriviality_cert_v1.lines_added_u32=10`
- `nontriviality_cert_v1.lines_deleted_u32=1`
- `nontriviality_cert_v1.touched_paths_u32=1`
- touched path: `orchestrator/omega_v18_0/goal_synthesizer_v1.py`

Axis gate decision:
`.../promotion/axis_gate_decision_v1.json`

- `axis_gate_required_b=false`
- `axis_gate_exempted_b=true`
- `axis_gate_reason_code=EXEMPTED`
- `effective_touched_paths=["orchestrator/omega_v18_0/goal_synthesizer_v1.py"]`

Meta-core verify:

- `meta_core_promo_verify_receipt_v1.json` -> `pass=true`
- `meta_core_promo_verify_out_v1.json` -> `verdict=VALID`

### Step G: Promotion + activation succeeded

Promotion receipt (primary):
`.../promotion/sha256_29fb8012....omega_promotion_receipt_v1.json`

- `result.status=PROMOTED`
- `result.route=ACTIVE`
- `declared_class=FRONTIER_HEAVY`
- `effect_class=EFFECT_HEAVY_OK`
- `promotion_bundle_hash=sha256:6afc4bfd5d5f20a544a202bda54c7225d192e9991966cccc4a23af24f12a94fd`
- `utility_proof_hash=sha256:ba944451541946811c34bd7bd58b34676fbac1e77adaa28fb98523fe34d1d4b8`

Activation receipt:
`.../activation/sha256_a1250e15....omega_activation_receipt_v1.json`

- `activation_success=true`
- `pass=true`
- `activation_method=ATOMIC_POINTER_SWAP`
- `healthcheck_result=PASS`

---

## 5) Exact Patch / FDiff Details

### 5.1 Promotion bundle -> CCAP -> patch chain

Promotion bundle file:
`.../subruns/1da7bba6fb8d81c6_rsi_ge_symbiotic_optimizer_sh1_v0_1/promotion/sha256_6afc4bfd5d5f20a544a202bda54c7225d192e9991966cccc4a23af24f12a94fd.omega_promotion_bundle_ccap_v1.json`

- `ccap_relpath=ccap/sha256_7e8625e314f05eaaa2ca28743ec7915113a4c338f82dddb5300fda2ca8496c81.ccap_v1.json`
- `patch_relpath=ccap/blobs/sha256_53af22de145cd3b7af0a735a59434f3afe7387ef8720b29d83cd02292c7e368a.patch`

CCAP payload file:
`.../subruns/.../ccap/sha256_7e8625e314f05eaaa2ca28743ec7915113a4c338f82dddb5300fda2ca8496c81.ccap_v1.json`

- `payload.kind=PATCH`
- `payload.patch_blob_id=sha256:53af22de145cd3b7af0a735a59434f3afe7387ef8720b29d83cd02292c7e368a`

### 5.2 Patch statistics

Patch file:
`.../subruns/.../ccap/blobs/sha256_53af22de145cd3b7af0a735a59434f3afe7387ef8720b29d83cd02292c7e368a.patch`

- line count: `24`
- byte size: `870`
- `git apply --stat`:
  - `orchestrator/omega_v18_0/goal_synthesizer_v1.py | 11 ++++++++++-`
  - `1 file changed, 10 insertions(+), 1 deletion(-)`
- `git apply --numstat`:
  - `10  1  orchestrator/omega_v18_0/goal_synthesizer_v1.py`

### 5.3 Full patch body

```diff
--- a/orchestrator/omega_v18_0/goal_synthesizer_v1.py
+++ b/orchestrator/omega_v18_0/goal_synthesizer_v1.py
@@ -120,7 +120,7 @@
 
 def _slug(value: str) -> str:
     out = _GOAL_ID_TOKEN_RE.sub("_", str(value).strip().lower()).strip("_")
-    return out or "x"
+    return _ge_wire_call_edge_grow_ad7ee6800c3(out or "x")
 
 
 def _enabled_campaigns_by_capability(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
@@ -911,3 +911,12 @@
 
 
 __all__ = ["suppressed_capability_ids_from_episodic_memory", "synthesize_goal_queue"]
+
+# ge_code_rewrite_ast:grow_ad7ee6800c34a869_0000_2509891444d9
+def _ge_wire_call_edge_grow_ad7ee6800c3(value):
+    if isinstance(value, str):
+        normalized = str(value).strip("_")
+        while "__" in normalized:
+            normalized = normalized.replace("__", "_")
+        return normalized or "x"
+    return value
```

---

## 6) Additional Technical Signals

- Lane final receipt (`.../long_run/lane/lane_receipt_final.long_run_lane_v1.json`):
  - `lane_name=FRONTIER`
  - reason codes include `MILESTONE_FORCE_SH1_FRONTIER`

- Eval report (`.../long_run/eval/sha256_c88000....eval_report_v1.json`):
  - `classification=IMPROVING`
  - `frontier_attempts_u64=1`
  - `heavy_ok_count_by_capability.RSI_GE_SH1_OPTIMIZER=1`

- Heavy forcing markers in tick index row 4:
  - `forced_frontier_attempt_b=true`
  - `forced_heavy_sh1_b=true`
  - `sh1_dispatch_forced_heavy_b=true`
  - `sh1_dispatch_wiring_locus_relpath=orchestrator/omega_v18_0/goal_synthesizer_v1.py`

---

## 7) Integrity Fingerprints (Key Files)

- `runs/p16_repin_heavy_only_hunt_fast_v1/LONG_RUN_STOP_RECEIPT_v1.json` -> `sha256:8a6a718fe85815302f8266dd7cf0875cfd010607555d052ea498c4c3bda5ed49`
- `runs/p16_repin_heavy_only_hunt_fast_v1/index/long_run_tick_index_v1.jsonl` -> `sha256:bf99f9679416292dffc7028fb9249bb79bc7f638233bae112c603cfb212a0134`
- `.../verifier/sha256_38094791....ccap_receipt_v1.json` -> `sha256:5bf74cdc62fb3890f7032979e4eee605dce3a63ae6a87858efcc99c28617ecd8`
- `.../promotion/sha256_ba944451....utility_proof_receipt_v1.json` -> `sha256:4a677b915f5677d89f6c898e4d77af7f822ac2fd13dbf388119671a1022ad764`
- `.../promotion/sha256_29fb8012....omega_promotion_receipt_v1.json` -> `sha256:a1a9fab298412d9b00470d91288353364206c6740776b50d282abf036d60c6d4`
- `.../activation/sha256_a1250e15....omega_activation_receipt_v1.json` -> `sha256:8dd59bc845d0e568b30c8680df08facec508690415ed8e22cd3b2e61742e8080`
- `.../promotion/sha256_6afc4bfd....omega_promotion_bundle_ccap_v1.json` -> `sha256:b0a93d603870e89839085caa9cfcabd14a83c31974d8df3e97f235837374908b`
- `.../ccap/sha256_7e8625e3....ccap_v1.json` -> `sha256:687b72844f756dde7147f38c589e1c6420138e5c0a38287854ef29b41a92d9d0`
- `.../ccap/blobs/sha256_53af22de....patch` -> `sha256:53af22de145cd3b7af0a735a59434f3afe7387ef8720b29d83cd02292c7e368a`

---

## 8) Notable Nuance (Non-blocking but worth recording)

`ge_preflight_loop_breaker_diagnostic_v1.json` in the subrun reports:

- `reason_code=VERIFY_ERROR:PATCH_PREFLIGHT_APPLY_CHECK_FAILED`
- `diagnostic_only_active_b=false`
- `repeat_count_u64=1`

Despite that diagnostic artifact, the authoritative chain for tick 4 shows:

- dispatch return code `0`
- subverifiers `VALID`
- CCAP `PASS/PROMOTE`
- utility proof `UTILITY_OK` and `utility_ok_b=true`
- promotion status `PROMOTED`
- activation `PASS`
- stop reason `HEAVY_PROMOTED`

So this diagnostic exists but did not block the successful heavy promotion outcome in this run.

