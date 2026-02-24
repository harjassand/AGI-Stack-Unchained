# P17 Forcing-Off Compounding Validation Forensics (Thorough)

Generated (UTC): 2026-02-24 00:58:08Z

## Scope

- Target run: `runs/p17_validation_forcing_off_compounding_20260224T005246Z`
- Launch invocation used:
  - `PYTHONPATH='.:CDEL-v2:Extension-1/agi-orchestrator' OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B=0 OMEGA_MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64=0 python3 scripts/run_long_disciplined_loop_v1.py --campaign_pack campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json --run_root runs/p17_validation_forcing_off_compounding_20260224T005246Z --max_ticks 220 --stop_on_heavy_promoted false --soak_after_first_heavy_promoted_ticks 20`
- Goal: validate P17 compounding criteria in forcing-off mode and capture full receipt chain.

---

## 1) Final Outcome (Ground Truth)

The run did **not** reach the P17 milestone. It halted at tick 3 due state verifier invalidation.

- Stop receipt: `runs/p17_validation_forcing_off_compounding_20260224T005246Z/LONG_RUN_STOP_RECEIPT_v1.json`
- `halt_reason_code`: `STATE_VERIFIER_INVALID`
- `halt_tick_u64`: `3`
- `state_verifier_reason_code`: `MISSING_STATE_INPUT`
- `detail.state_verifier_failure_detail_hash`: `null`
- `detail.state_verifier_replay_fail_detail_hash`: `null`

File hash:

- `LONG_RUN_STOP_RECEIPT_v1.json` -> `sha256:d75b6835bf31fed69e6c088be26cd0f4a3e40475551c7a888c7e4237dc3616df`

---

## 2) P17.0 Milestone Check (Pass/Fail)

From the final tick index row (`tick_u64=3`):

- `heavy_promoted_total_u64=0`
- `first_heavy_promoted_tick_u64=null`
- `soak_complete_tick_u64=null`
- `hard_stop_reason_code=STATE_VERIFIER_INVALID`

Criteria verdict:

- `heavy_promoted_total_u64 >= 3 within 220 ticks` -> **FAIL** (`0`)
- `SOAK_COMPLETE after first heavy promotion` -> **FAIL** (no first heavy promotion occurred)
- `No stop due PATCH_APPLY_LOOP` -> **PASS** (not observed)
- `No stop due UTILITY_DROUGHT` -> **PASS** (not observed)
- `No stop due PROBE_REGISTRY_MISSING` -> **PASS** (not observed)
- `No verifier invalidation stop` -> **FAIL** (`STATE_VERIFIER_INVALID`)

---

## 3) What Happened (Ticks 1-3)

### 3.1 Tick timeline

- Tick 1:
  - `lane_name=BASELINE`
  - `selected_capability_id=RSI_GE_SH1_OPTIMIZER`
  - `frontier_attempt_counted_b=true`
  - `heavy_utility_ok_b=false`, `heavy_promoted_b=false`
  - `ccap_receipt_present_b=false`, `promotion_status=SKIPPED`, `promotion_reason_code=NO_PROMOTION_BUNDLE`
  - dispatch `return_code=0`; verifier stdout: `VALID` + `NO_CCAP_CANDIDATE`
- Tick 2:
  - same pattern as tick 1
  - dispatch `return_code=0`; verifier stdout: `VALID` + `NO_CCAP_CANDIDATE`
- Tick 3:
  - same routing/classification pattern
  - dispatch `return_code=1`; campaign stderr ends in `OmegaV18Error: INVALID:VERIFY_ERROR`
  - still `subverifier_status=VALID` and `promotion_status=SKIPPED` (`NO_PROMOTION_BUNDLE`)
  - run halts with `STATE_VERIFIER_INVALID` / `MISSING_STATE_INPUT`

### 3.2 Non-forced confirmation

All tick index rows and dispatch receipts indicate forcing remained off:

- `forced_frontier_attempt_b=false`
- `forced_heavy_sh1_b=false`
- `sh1_dispatch_forced_heavy_b=false`
- `dispatch_env_overrides_v1.applied_env_overrides={}`

---

## 4) Run Configuration That Produced This Outcome

Launch manifest:
`runs/p17_validation_forcing_off_compounding_20260224T005246Z/configs/long_run_launch_manifest_v1.json`

Key controls observed in manifest/env receipts:

- `execution.max_ticks=220`
- `OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B=0`
- `OMEGA_MILESTONE_FORCE_SH1_FRONTIER_UNTIL_TICK_U64=0`
- `OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B=1`
- `resolved_orch_llm_backend=mlx`
- `resolved_orch_model_id=mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`

CLI flags used for this launch:

- `--stop_on_heavy_promoted false`
- `--soak_after_first_heavy_promoted_ticks 20`

---

## 5) How It Halted (Evidence Chain)

### Step A: Lane + mission generated baseline frontier work

Lane receipt (`.../state/long_run/lane/lane_receipt_final.long_run_lane_v1.json`):

- `lane_name=BASELINE`
- `reason_codes=["CADENCE_BASELINE"]`

Mission ingest receipt (`.../state/long_run/mission/sha256_a498...mission_goal_ingest_receipt_v1.json`):

- `status=MISSION_GOAL_ADDED`
- includes `goal_auto_10_mission_rsi_ge_sh1_optimizer_000003_01` in goals list

### Step B: Routing and decision selected SH1 optimizer without forcing

Dependency routing receipt (`.../state/long_run/debt/sha256_ddba...dependency_routing_receipt_v1.json`):

- `routing_selector_id=NON_MARKET`
- `selected_capability_id=RSI_GE_SH1_OPTIMIZER`
- `selected_declared_class=FRONTIER_HEAVY`
- `forced_frontier_attempt_b=false`
- `reason_codes=["NO_DEPENDENCY_ROUTING"]`

Decision plan (`.../state/decisions/sha256_1093...omega_decision_plan_v1.json`):

- `action_kind=RUN_CAMPAIGN`
- `campaign_id=rsi_ge_symbiotic_optimizer_sh1_v0_1`
- `capability_id=RSI_GE_SH1_OPTIMIZER`
- `tie_break_path=["POLICY_VM_V1"]`

### Step C: Dispatch attempted normally; tick 3 campaign exited with VERIFY_ERROR

Dispatch receipt (`.../state/dispatch/d82113109f5ac38f/sha256_5feb...omega_dispatch_receipt_v1.json`):

- `dispatch_attempted_b=true`
- `return_code=1`
- `dispatch_env_overrides_v1.forced_heavy_b=false`
- `dispatch_env_overrides_v1.applied_env_overrides={}`

Dispatch stderr (`.../state/dispatch/d82113109f5ac38f/stderr.log`) ends with:

- `cdel.v18_0.omega_common_v1.OmegaV18Error: INVALID:VERIFY_ERROR`

### Step D: Verifier remained VALID but reported no candidate

Subverifier receipt (`.../verifier/sha256_3757...omega_subverifier_receipt_v1.json`):

- `result.status=VALID`
- `verifier_module=cdel.v18_0.verify_ccap_v1`

Verifier stdout (`.../verifier/stdout.log`):

- `VALID`
- `NO_CCAP_CANDIDATE`

### Step E: Promotion skipped; no bundle/utility proof

Promotion receipt (`.../promotion/sha256_c1bb...omega_promotion_receipt_v1.json`):

- `result.status=SKIPPED`
- `result.reason_code=NO_PROMOTION_BUNDLE`
- `result.route=NONE`
- `declared_class=FRONTIER_HEAVY`
- `effect_class=EFFECT_HEAVY_NO_UTILITY`
- `promotion_bundle_hash=sha256:000...000`
- `utility_proof_hash=null`

### Step F: Hard stop was verifier invalid with missing input detail

Stop receipt (`LONG_RUN_STOP_RECEIPT_v1.json`):

- `halt_reason_code=STATE_VERIFIER_INVALID`
- `state_verifier_reason_code=MISSING_STATE_INPUT`
- `state_verifier_failure_detail_hash=null`
- `state_verifier_replay_fail_detail_hash=null`
- `last_valid_state_dir_relpath=.../tick_000002/.../state`

---

## 6) Patch / FDiff Status

No promotable candidate existed in this run:

- no `ccap_receipt_v1.json` artifacts under run root
- no `utility_proof_receipt_v1.json` artifacts
- promotion receipts all show `NO_PROMOTION_BUNDLE`

Therefore:

- no promotion bundle -> no patch chain -> no fdiff/patch stats to report for P17 validation run

---

## 7) Additional Technical Signals

- Eval report (`.../long_run/eval/sha256_5223...eval_report_v1.json`):
  - `classification=FLAT_OR_REGRESS`
  - `frontier_attempts_u64=3`
  - `heavy_no_utility_count_by_capability.RSI_GE_SH1_OPTIMIZER=3`
  - `heavy_ok_count_by_capability={}`

- Dependency debt state (`.../long_run/debt/sha256_d2be...dependency_debt_state_v1.json`):
  - `frontier_attempts_u64=3`
  - `reason_code=FRONTIER_ATTEMPT_COUNTED`
  - `last_frontier_attempt_debt_key=frontier:rsi_ge_sh1_optimizer`

- Soak artifacts exist but indicate not ready (no heavy-promotion-triggered soak window reached):
  - `native_wasm_shadow_soak_summary_v1`: `readiness_gate_result=FAIL`, reasons include `NO_SHADOW_MODULE`
  - `native_wasm_shadow_soak_receipt_v1`: `rows=[]`

- No `ge_preflight_loop_breaker_diagnostic_v1.json` artifact found in this run.

---

## 8) Integrity Fingerprints (Key Files)

- `runs/p17_validation_forcing_off_compounding_20260224T005246Z/LONG_RUN_STOP_RECEIPT_v1.json` -> `sha256:d75b6835bf31fed69e6c088be26cd0f4a3e40475551c7a888c7e4237dc3616df`
- `runs/p17_validation_forcing_off_compounding_20260224T005246Z/index/long_run_tick_index_v1.jsonl` -> `sha256:fa0c2068a7459f910e178281314c558b00fb4a57362e8b4806e1ef76b1f159ad`
- `runs/p17_validation_forcing_off_compounding_20260224T005246Z/configs/long_run_launch_manifest_v1.json` -> `sha256:caf57e21b4f43303bbdc97dc7a20d0c8164006250052f141e552afa2e76410f4`
- `runs/p17_validation_forcing_off_compounding_20260224T005246Z/run_env_receipt_v1.json` -> `sha256:22b0c093269d8a84fc6a07396d01615ca4b6a1b2fe7b04fe5428908fa3d11816`
- `.../long_run/debt/sha256_ddba099d...dependency_routing_receipt_v1.json` -> `sha256:c935eba5e22b1a1c2a11c2fac3e7b69227407edf058a52275e515732b2500ef6`
- `.../long_run/debt/sha256_d2be5625...dependency_debt_state_v1.json` -> `sha256:2c28fff195fc567699c1c1aa0a7adacbe7c6433bcbf109464f9b7d2c14e7a96c`
- `.../decisions/sha256_1093b7d3...omega_decision_plan_v1.json` -> `sha256:2f1c4f09ba9a20a193eab453d83c110cefbacf6a72da27eb95aec90f8345d89f`
- `.../dispatch/d82113109f5ac38f/sha256_5feb94dc...omega_dispatch_receipt_v1.json` -> `sha256:df13a8fedaac2c840184d614d719ade7cc4b49888434b7b61b47478346067122`
- `.../dispatch/d82113109f5ac38f/verifier/sha256_37576943...omega_subverifier_receipt_v1.json` -> `sha256:a9d8d60771bdb798c90112430061a0bc9b214df5b6238cb09faeb5ad9a016c1f`
- `.../dispatch/d82113109f5ac38f/promotion/sha256_c1bbc56c...omega_promotion_receipt_v1.json` -> `sha256:84c8d5c9d5b7a812c9ea5c822e15cfd583355f494f7d37457e03e2a0eafaf236`
- `.../long_run/eval/sha256_52230b71...eval_report_v1.json` -> `sha256:22d19871537dca902d90e527d1167353dec98a923429f46ad17f27631bf05f7e`
- `.../long_run/lane/lane_receipt_final.long_run_lane_v1.json` -> `sha256:90202e7b28a34d61dcbbd9e7b192b057ed7643a0bd8c8440c40e13525f42778a`
- `.../native/shadow/soak/sha256_50ee1d01...native_wasm_shadow_soak_summary_v1.json` -> `sha256:a70f410167139f6baa2f3b98ee6e51e82541469d2d6c89a778227b3f4f83aa2b`
- `.../native/shadow/soak/sha256_fb96493d...native_wasm_shadow_soak_receipt_v1.json` -> `sha256:30cf5ae947c955c8209760c22aef00c90941e341834750b4e8298a5b5a53ff5d`

---

## 9) Notable Nuance (Blocking)

This P17 run did not fail for patch-loop/drought/probe reasons; it failed earlier due verifier invalidation with missing state input metadata:

- `state_verifier_reason_code=MISSING_STATE_INPUT`
- no emitted failure-detail sidecar hashes (`null` for both detail hash fields)

Given P17 acceptance explicitly forbids verifier invalidation stops, this is the immediate blocker before compounding-loop metrics can be evaluated.
