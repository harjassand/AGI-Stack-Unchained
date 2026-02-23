# Utility Drought Forensics (60-Tick Forcing-Off Run)

Generated: 2026-02-23

## Scope and Run Roots

- Forcing-off run (60 ticks): `runs/p13_canary_off_60`
- Slow EK evidence run (EK actually executed and passed): `runs/p14_micro_canary_15`

---

## 1) Slow Tick CCAP Receipt (EK Ran) + SMOKE_EK Sizing Inputs

### 1.1 Slow tick selected

Source row: `runs/p14_micro_canary_15/index/long_run_tick_index_v1.jsonl` (`tick_u64=2`)

```json
{
  "tick_u64": 2,
  "duration_s": 166,
  "ccap_receipt_hash": "sha256:ec0becb4e439da2f480a9c40a9358adffb571c36605949fd1f1384e80f519bc8",
  "ccap_eval_status": "PASS",
  "ccap_decision": "PROMOTE",
  "ccap_cost_vector_wall_ms": 119388,
  "ccap_cost_vector_cpu_ms": 9777,
  "ccap_effective_budget_tuple_time_ms_max": 600000,
  "ccap_effective_budget_tuple_stage_cost_budget": 600000,
  "resolved_orch_llm_backend": "mlx",
  "resolved_orch_model_id": "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
  "out_dir": "/Users/harjas/AGI-Stack-Unchained/runs/p14_micro_canary_15/tick_000002"
}
```

### 1.2 `ccap_receipt_v1.json` from slow tick where EK ran

Path: `runs/p14_micro_canary_15/tick_000002/daemon/rsi_omega_daemon_v19_0/state/dispatch/4261f8d385a64530/verifier/sha256_ec0becb4e439da2f480a9c40a9358adffb571c36605949fd1f1384e80f519bc8.ccap_receipt_v1.json`
File SHA-256: `b92232c494326f924c5496e89be510b812e7097547643bef753f6a7a4f8422d0`

Contains required fields:
- `effective_budget.tuple`
- `cost_vector`
- `resolved backend/model` are not part of this receipt schema; they are present in run env/launch manifest and tick index row above.
- `eval profile` fields are not present in this receipt schema (only `ek_id` and budget/profile IDs).

```json
{
  "applied_tree_id": "sha256:e5ed224f90b2805cfabab28b0d12f69fa0af9006b801a446cb32a78f77ef9a66",
  "auth_hash": "sha256:0a4cacd34928f101b01adb4ca6caa6ac57f77735c9275af9a05c08e482b32c38",
  "base_tree_id": "sha256:685b8bec968a7012930a89122a43d9f80da83a279b872824c5038718340afb07",
  "ccap_id": "sha256:5d71c827d4c17d557a40376d7a8102f0c87960d1be61370b723a8a98adb34479",
  "cost_vector": {
    "cpu_ms": 9777,
    "disk_mb": 2736,
    "fds": 4,
    "mem_mb": 633,
    "procs": 0,
    "threads": 0,
    "wall_ms": 119388
  },
  "decision": "PROMOTE",
  "determinism_check": "PASS",
  "effective_budget": {
    "env_overrides": {
      "OMEGA_CCAP_DISK_MB_MAX": "8192"
    },
    "limits": {
      "cpu_ms_max": 600000,
      "disk_mb_max": 8192,
      "fds_max": 256,
      "mem_mb_max": 4096,
      "net": "forbidden",
      "procs_max": 64,
      "threads_max": 256,
      "wall_ms_max": 600000
    },
    "profile_id": "sha256:fa091c735bdf9cb0be5064491b121ea175a8c6e08f4db9b3c24f2f8dc5cccedc",
    "tuple": {
      "artifact_bytes_max": 8589934592,
      "disk_mb_max": 8192,
      "stage_cost_budget": 600000,
      "time_ms_max": 600000
    }
  },
  "ek_id": "sha256:ea51a38e9753b81c09e55c7fb71c142ef74e549a3c438c6f3092fe2c8abda525",
  "eval_status": "PASS",
  "logs_hash": "sha256:7bad3daf47042e6c976d1e3b03e46fa9009f94595d5adf39ad250120f978b4c3",
  "op_pool_id": "sha256:c4ed583b732c32189a549fd7da88f5fa2de3044b0b9ce07c99358453ccbcc7a7",
  "realized_out_id": "sha256:15f4c8c3ce00445cd627297750025454c9445a8b676ab3de49806009a0d02940",
  "schema_version": "ccap_receipt_v1",
  "score_base_summary": {
    "activation_success_u64": 0,
    "median_stps_non_noop_q32": 341789394,
    "non_noop_ticks_per_min_f64": 0,
    "promotions_u64": 0
  },
  "score_cand_summary": {
    "activation_success_u64": 0,
    "median_stps_non_noop_q32": 414926037,
    "non_noop_ticks_per_min_f64": 0,
    "promotions_u64": 0
  },
  "score_delta_summary": {
    "activation_success_u64": 0,
    "median_stps_non_noop_q32": 73136643,
    "non_noop_ticks_per_min_f64": 0,
    "promotions_u64": 0
  },
  "scorecard_summary": {
    "activation_success_u64": 0,
    "median_stps_non_noop_q32": 414926037,
    "non_noop_ticks_per_min_f64": 0,
    "promotions_u64": 0
  }
}
```

### 1.3 Inputs for default `SMOKE_EK` subset size `K` and tuple

Suite metadata path: `campaigns/rsi_omega_daemon_v19_0_long_run_v1/eval/omega_math_science_task_suite_v1.json`

```json
{
  "schema_version": "omega_math_science_task_suite_v1",
  "suite_id": "omega_math_science_task_suite_v1",
  "total_problems_u64": 60,
  "in_distribution_count": 48,
  "heldout_count": 12
}
```

Observed from slow EK tick (`tick 2`):
- `cost_vector.wall_ms = 119388` ms over `total_problems_u64 = 60`
- Approx per-problem wall time (linear estimate): `119388 / 60 = 1989.8 ms`

Derived `SMOKE_EK` defaults (target single-digit/low-teens seconds):
- Recommended `K = 5` (expected wall time ~`5 * 1989.8 ~= 9949 ms` before overhead)
- Recommended tuple for smoke mode:
  - `time_ms_max = 60000`
  - `stage_cost_budget = 60000`
  - `disk_mb_max = 1024`
  - `artifact_bytes_max = 536870912` (512 MiB)

Rationale:
- Leaves ~6x margin above expected ~10s wall time.
- Keeps smoke budget sharply below production tuple (`600000`, `600000`, `8192`, `8589934592`).

---

## 1.4 Run-env and launch-manifest backend/model checks

Requested index paths do not exist in these runs:
- `runs/p13_canary_off_60/index/run_env_receipt_v1.json` -> missing
- `runs/p13_canary_off_60/index/long_run_launch_manifest_v1.json` -> missing

Actual canonical locations used:
- `runs/p13_canary_off_60/run_env_receipt_v1.json`
- `runs/p13_canary_off_60/configs/long_run_launch_manifest_v1.json`
- `runs/p13_canary_off_60/launch/sha256_5da903a6813705ebf285fdbc59bfde2ad01ae1f85f7cd0443a259c205c85f4e4.long_run_launch_manifest_v1.json`

`run_env_receipt_v1.json`:

```json
{"created_unix_s":1771823285,"env":{"OMEGA_ALLOW_SIMULATE_ACTIVATION":"1","OMEGA_CCAP_ALLOW_DIRTY_TREE":"1","OMEGA_CCAP_DISK_MB_MAX":"8192","OMEGA_META_CORE_ACTIVATION_MODE":"simulate","OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B":"0","OMEGA_NET_LIVE_OK":"0","OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B":"1","ORCH_LLM_BACKEND":"mlx","ORCH_MLX_MODEL":"mlx-community/Qwen2.5-Coder-14B-Instruct-4bit","PYTHONPATH":".:CDEL-v2:Extension-1/agi-orchestrator"},"receipt_id":"sha256:a3966b678921be152d78ed4f6cbc19fc25feb0bc57e0a7cdfbde4def424f2fae","resolved_orch_llm_backend":"mlx","resolved_orch_model_id":"mlx-community/Qwen2.5-Coder-14B-Instruct-4bit","schema_name":"run_env_receipt_v1","schema_version":"v1"}
```

`long_run_launch_manifest_v1.json`:

```json
{"campaign_pack_hash":"sha256:0a478fca3a5f3d55b49b60703032f34a799b66fdfa35bcb99a75b3541022c802","campaign_pack_relpath":"campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json","created_unix_s":1771823285,"env":{"OMEGA_ALLOW_SIMULATE_ACTIVATION":"1","OMEGA_CCAP_ALLOW_DIRTY_TREE":"1","OMEGA_CCAP_DISK_MB_MAX":"8192","OMEGA_META_CORE_ACTIVATION_MODE":"simulate","OMEGA_MILESTONE_FORCE_SH1_FRONTIER_B":"0","OMEGA_NET_LIVE_OK":"0","OMEGA_RETENTION_PRUNE_CCAP_EK_RUNS_B":"1","ORCH_LLM_BACKEND":"mlx","ORCH_MLX_MODEL":"mlx-community/Qwen2.5-Coder-14B-Instruct-4bit","PYTHONPATH":".:CDEL-v2:Extension-1/agi-orchestrator"},"env_receipt_hash":"sha256:e7dff8ca4abef3df2a6e61495a76f7205249f2c99e9c047c66e1fe6a7e619a6f","execution":{"anchor_every_u64":100,"canary_every_u64":10,"force_eval_b":false,"force_lane":null,"max_disk_bytes":21474836480,"max_ticks":60,"retain_last_u64":200,"start_tick_u64":1},"long_run_profile_hash":"sha256:4f9483a8cc30580b3cbe2115b25a0eda036b6e747001c337e3e580795a7c1895","manifest_id":"sha256:d3390e259493af2fb2519978a9434ddaf6116707e9d763a8a86ce401f1be3bf1","manifest_relpath":"runs/p13_canary_off_60/configs/long_run_launch_manifest_v1.json","resolved_orch_llm_backend":"mlx","resolved_orch_model_id":"mlx-community/Qwen2.5-Coder-14B-Instruct-4bit","run_root_relpath":"runs/p13_canary_off_60","schema_name":"long_run_launch_manifest_v1","schema_version":"v19_0"}
```

---

## 1.5 Frontier-heavy tick with `frontier_attempt_counted_b=true` and `heavy_utility_ok_b=false`

Selected tick: `58` in `runs/p13_canary_off_60`

```json
{
  "tick_u64": 58,
  "frontier_attempt_counted_b": true,
  "declared_class": "FRONTIER_HEAVY",
  "lane_name": "BASELINE",
  "heavy_utility_ok_b": false,
  "promotion_reason_code": "NO_UTILITY_GAIN_SHADOW",
  "selected_capability_id": "RSI_KNOWLEDGE_TRANSPILER",
  "out_dir": "/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000058",
  "state_dir": "/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state",
  "ccap_receipt_present_b": false,
  "utility_proof_hash": "sha256:51d4b7387a10dbf4324cac1fc55a294738f0ec784952274ebe357f4cf674d600",
  "eval_report_hash": "sha256:27e7d13f3a3c1428cedd7997f86a86ee8cecf67ceb115b70eddc54cf985e659e"
}
```

### Requested artifacts (hash + path)

- `state/decisions/*.omega_decision_plan_v1.json`
  - `sha256:708186e601952e73c6e14f647d11ba19e89f696c52510331cfca9b251ed6f708` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/decisions/sha256_708186e601952e73c6e14f647d11ba19e89f696c52510331cfca9b251ed6f708.omega_decision_plan_v1.json`
  - `sha256:78d49984b311b2f192461c93bbc2300192d665ee5d883b11ce7f17a99badcbad` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/decisions/sha256_78d49984b311b2f192461c93bbc2300192d665ee5d883b11ce7f17a99badcbad.omega_decision_plan_v1.json`

- `state/dispatch/*/dispatch_receipt*.omega_dispatch_receipt_v1.json`
  - `sha256:d88f23a497b9ed238faca2e0ffe42adda1546d246c8b639060f37f4db342a030` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/dispatch/b348c97ea252d4dc/sha256_d88f23a497b9ed238faca2e0ffe42adda1546d246c8b639060f37f4db342a030.omega_dispatch_receipt_v1.json`

- `state/dispatch/*/verifier/*.omega_subverifier_receipt_v1.json`
  - `sha256:6cdd3cbe00c5fbfd7983a62ca72187592eb699f282a5ef1ac2158a8fb81ba436` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/dispatch/b348c97ea252d4dc/verifier/sha256_6cdd3cbe00c5fbfd7983a62ca72187592eb699f282a5ef1ac2158a8fb81ba436.omega_subverifier_receipt_v1.json`

- `state/dispatch/*/verifier/*.ccap_receipt_v1.json` (if present)
  - None in tick 58 (index row has `ccap_receipt_present_b=false`).

- `state/dispatch/*/verifier/*.utility_proof_receipt_v1.json` (if present)
  - Utility proof receipt is present under promotion subdir:
  - `sha256:51d4b7387a10dbf4324cac1fc55a294738f0ec784952274ebe357f4cf674d600` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/dispatch/b348c97ea252d4dc/promotion/sha256_51d4b7387a10dbf4324cac1fc55a294738f0ec784952274ebe357f4cf674d600.utility_proof_receipt_v1.json`

- `state/dispatch/*/observation/*.omega_observation_report_v1.json` (or observation hash in index)
  - No `state/dispatch/*/observation/` artifact for tick 58.
  - Observation artifact exists at:
  - `sha256:9dca57099f8105276a3d2b0af051154a872abfb7554987fe3d4bbbd3e92936e5` -> `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/observations/sha256_9dca57099f8105276a3d2b0af051154a872abfb7554987fe3d4bbbd3e92936e5.omega_observation_report_v1.json`

- Final lane receipt: `state/long_run/lane/lane_receipt_final.long_run_lane_v1.json`
  - Path: `runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/long_run/lane/lane_receipt_final.long_run_lane_v1.json`
  - `receipt_id` inside file: `sha256:b4a1408e81fb114beef75a2c7644deb0b5416d1bc775ff08596ee6034505f60c`

---

## 2) Utility Drought Summary over 60-Tick Forcing-Off Run

Source: `runs/p13_canary_off_60/index/long_run_tick_index_v1.jsonl`

### 2.1 Counts of `utility_proof_reason_code`

```json
[
  {
    "utility_proof_reason_code": "<null>",
    "count": 12
  },
  {
    "utility_proof_reason_code": "UTILITY_OK",
    "count": 48
  }
]
```

### 2.2 Counts of `promotion_reason_code`

```json
[
  {
    "promotion_reason_code": "CCAP_RECEIPT_REJECTED",
    "count": 48
  },
  {
    "promotion_reason_code": "NO_UTILITY_GAIN_SHADOW",
    "count": 12
  }
]
```

### 2.3 Ticks where `frontier_attempt_counted_b=true`

`4,8,14,18,24,28,34,38,44,48,54,58`

### 2.4 Ticks by selected capability ID

- `RSI_GE_SH1_OPTIMIZER`

`1,2,3,5,6,7,9,10,11,12,13,15,16,17,19,20,21,22,23,25,26,27,29,30,31,32,33,35,36,37,39,40,41,42,43,45,46,47,49,50,51,52,53,55,56,57,59,60`

- `RSI_KNOWLEDGE_TRANSPILER`

`4,8,14,18,24,28,34,38,44,48,54,58`

- `RSI_OMEGA_NATIVE_MODULE`

`(none in this run)`

### 2.5 Existing miner output

Path: `runs/p13_canary_off_60/index/miner_utility_blockers_last60_v1.json`

```json
{"counted_heavy_attempts_u64":12,"histogram_by_reason_capability":[{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","count_u64":12,"reason_code":"PROBE_MISSING"}],"rows_scanned_u64":60,"top_examples_v1":[{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","count_u64":12,"examples_v1":[{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","hard_task_baseline_init_b":false,"hard_task_delta_q32":0,"predicted_hard_task_delta_q32":0,"state_dir":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state","thresholds_v1":{"hard_task_min_gain_count_u64":1,"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"tick_u64":58,"utility_proof_reason_code":"PROBE_MISSING","utility_receipt_path":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000058/daemon/rsi_omega_daemon_v19_0/state/dispatch/b348c97ea252d4dc/promotion/sha256_51d4b7387a10dbf4324cac1fc55a294738f0ec784952274ebe357f4cf674d600.utility_proof_receipt_v1.json"},{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","hard_task_baseline_init_b":false,"hard_task_delta_q32":0,"predicted_hard_task_delta_q32":0,"state_dir":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000054/daemon/rsi_omega_daemon_v19_0/state","thresholds_v1":{"hard_task_min_gain_count_u64":1,"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"tick_u64":54,"utility_proof_reason_code":"PROBE_MISSING","utility_receipt_path":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000054/daemon/rsi_omega_daemon_v19_0/state/dispatch/4cb5fd0f0d937220/promotion/sha256_300fa42cc8dcd4c4b9951787d5bcecc9634399711874b6f76bab2e90a3e77d0d.utility_proof_receipt_v1.json"},{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","hard_task_baseline_init_b":false,"hard_task_delta_q32":0,"predicted_hard_task_delta_q32":0,"state_dir":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000048/daemon/rsi_omega_daemon_v19_0/state","thresholds_v1":{"hard_task_min_gain_count_u64":1,"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"tick_u64":48,"utility_proof_reason_code":"PROBE_MISSING","utility_receipt_path":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000048/daemon/rsi_omega_daemon_v19_0/state/dispatch/e575155d20a9808f/promotion/sha256_c3d2d3a5506cc775cfa6699d0128e57f0ff7cdfa4f27e8f4ead2dc6938434983.utility_proof_receipt_v1.json"},{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","hard_task_baseline_init_b":false,"hard_task_delta_q32":0,"predicted_hard_task_delta_q32":0,"state_dir":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000044/daemon/rsi_omega_daemon_v19_0/state","thresholds_v1":{"hard_task_min_gain_count_u64":1,"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"tick_u64":44,"utility_proof_reason_code":"PROBE_MISSING","utility_receipt_path":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000044/daemon/rsi_omega_daemon_v19_0/state/dispatch/1d848f45f980b2ba/promotion/sha256_60134f7f31d9603ee694a936c06ad105d9d011acd816f870a066a3da31d7b384.utility_proof_receipt_v1.json"},{"capability_id":"RSI_KNOWLEDGE_TRANSPILER","hard_task_baseline_init_b":false,"hard_task_delta_q32":0,"predicted_hard_task_delta_q32":0,"state_dir":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000038/daemon/rsi_omega_daemon_v19_0/state","thresholds_v1":{"hard_task_min_gain_count_u64":1,"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"tick_u64":38,"utility_proof_reason_code":"PROBE_MISSING","utility_receipt_path":"/Users/harjas/AGI-Stack-Unchained/runs/p13_canary_off_60/tick_000038/daemon/rsi_omega_daemon_v19_0/state/dispatch/0bb28b4a1e83c9f0/promotion/sha256_38fe3a479e6a7af160f5ee2996f9db20e2afde9e8a94fdfcdf4917995120e6e4.utility_proof_receipt_v1.json"}],"reason_code":"PROBE_MISSING"}]}
```

---

## 3) Capability Registry + Active Utility Policy + Long-Run Profile

### 3.1 Capability registry requested

Path: `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`

SHA-256: `c4d7a7bbb3f7c72e81cc4313eece5d518f6a78a00096216940af9b437e62c4e1`

JSON (current version):

```json
{"capabilities":[{"budget_cost_hint_q32":{"q":4294967296},"campaign_id":"rsi_omega_self_optimize_core_v1","campaign_pack_rel":"campaigns/rsi_omega_self_optimize_core_v1/rsi_omega_self_optimize_core_pack_v1.json","capability_id":"RSI_OMEGA_SELF_OPTIMIZE_CORE","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_self_optimize_core_v1","promotion_bundle_rel":"daemon/rsi_omega_self_optimize_core_v1/state/promotion/*.omega_core_opt_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_omega_self_optimize_core_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_self_optimize_core_v1"},{"budget_cost_hint_q32":{"q":2147483648},"campaign_id":"rsi_polymath_bootstrap_domain_v1","campaign_pack_rel":"campaigns/rsi_polymath_bootstrap_domain_v1/rsi_polymath_bootstrap_domain_pack_v1.json","capability_id":"RSI_POLYMATH_BOOTSTRAP_DOMAIN","cooldown_ticks_u64":50,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_polymath_bootstrap_domain_v1","promotion_bundle_rel":"daemon/rsi_polymath_bootstrap_domain_v1/state/promotion/*.polymath_bootstrap_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_polymath_bootstrap_domain_v1/state","verifier_module":"cdel.v18_0.verify_rsi_polymath_domain_v1"},{"budget_cost_hint_q32":{"q":2147483648},"campaign_id":"rsi_polymath_conquer_domain_v1","campaign_pack_rel":"campaigns/rsi_polymath_conquer_domain_v1/rsi_polymath_conquer_domain_pack_v1.json","capability_id":"RSI_POLYMATH_CONQUER_DOMAIN","cooldown_ticks_u64":25,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_polymath_conquer_domain_v1","promotion_bundle_rel":"daemon/rsi_polymath_conquer_domain_v1/state/promotion/*.polymath_conquer_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_polymath_conquer_domain_v1/state","verifier_module":"cdel.v18_0.verify_rsi_polymath_domain_v1"},{"budget_cost_hint_q32":{"q":2147483648},"campaign_id":"rsi_polymath_scout_v1","campaign_pack_rel":"campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json","capability_id":"RSI_POLYMATH_SCOUT","cooldown_ticks_u64":25,"enable_ccap":0,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_polymath_scout_v1","promotion_bundle_rel":"daemon/rsi_polymath_scout_v1/state/promotion/*.polymath_scout_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_polymath_scout_v1/state","verifier_module":"cdel.v18_0.verify_rsi_polymath_scout_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_sas_code_v12_0","campaign_pack_rel":"campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v1.json","capability_id":"RSI_SAS_CODE","cooldown_ticks_u64":1,"enabled":true,"orchestrator_module":"orchestrator.rsi_sas_code_v12_0","promotion_bundle_rel":"daemon/rsi_sas_code_v12_0/state/promotion/*.sas_code_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_sas_code_v12_0/state","verifier_module":"cdel.v12_0.verify_rsi_sas_code_v1"},{"budget_cost_hint_q32":{"q":6442450944},"campaign_id":"rsi_sas_metasearch_v16_1","campaign_pack_rel":"campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json","capability_id":"RSI_SAS_METASEARCH","cooldown_ticks_u64":50,"enabled":true,"orchestrator_module":"orchestrator.rsi_sas_metasearch_v16_1","promotion_bundle_rel":"daemon/rsi_sas_metasearch_v16_1/state/promotion/*.sas_metasearch_promotion_bundle_v2.json","risk_class":"MED","state_dir_rel":"daemon/rsi_sas_metasearch_v16_1/state","verifier_module":"cdel.v16_1.verify_rsi_sas_metasearch_v16_1"},{"budget_cost_hint_q32":{"q":8589934592},"campaign_id":"rsi_sas_val_v17_0","campaign_pack_rel":"campaigns/rsi_sas_val_v17_0/rsi_sas_val_pack_v17_0.json","capability_id":"RSI_SAS_VAL","cooldown_ticks_u64":50,"enabled":true,"orchestrator_module":"orchestrator.rsi_sas_val_v17_0","promotion_bundle_rel":"daemon/rsi_sas_val_v17_0/state/promotion/*.sas_val_promotion_bundle_v1.json","risk_class":"HIGH","state_dir_rel":"daemon/rsi_sas_val_v17_0/state","verifier_module":"cdel.v17_0.verify_rsi_sas_val_v1"},{"budget_cost_hint_q32":{"q":2147483648},"campaign_id":"rsi_ge_symbiotic_optimizer_sh1_v0_1","campaign_pack_rel":"campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1/rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json","capability_id":"RSI_GE_SH1_OPTIMIZER","cooldown_ticks_u64":25,"enable_ccap":1,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_ge_symbiotic_optimizer_sh1_v0_1","promotion_bundle_rel":"promotion/sha256_*.omega_promotion_bundle_ccap_v1.json","risk_class":"MED","state_dir_rel":".","verifier_module":"cdel.v18_0.verify_ccap_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_transfer_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_transfer_v1/rsi_omega_skill_transfer_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_TRANSFER","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_transfer_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_transfer_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_ontology_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_ontology_v1/rsi_omega_skill_ontology_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_ONTOLOGY","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_ontology_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_ontology_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_eff_flywheel_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_eff_flywheel_v1/rsi_omega_skill_eff_flywheel_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_EFF_FLYWHEEL","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_eff_flywheel_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_eff_flywheel_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_thermo_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_thermo_v1/rsi_omega_skill_thermo_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_THERMO","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_thermo_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_thermo_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_persistence_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_persistence_v1/rsi_omega_skill_persistence_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_PERSISTENCE","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_persistence_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_persistence_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_alignment_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_alignment_v1/rsi_omega_skill_alignment_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_ALIGNMENT","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_alignment_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_alignment_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_boundless_math_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_boundless_math_v1/rsi_omega_skill_boundless_math_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_BOUNDLESS_MATH","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_boundless_math_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_boundless_math_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_boundless_science_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_boundless_science_v1/rsi_omega_skill_boundless_science_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_boundless_science_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_boundless_science_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_swarm_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_swarm_v1/rsi_omega_skill_swarm_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_SWARM","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_swarm_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_swarm_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":1073741824},"campaign_id":"rsi_omega_skill_model_genesis_v1","campaign_pack_rel":"campaigns/rsi_omega_skill_model_genesis_v1/rsi_omega_skill_model_genesis_pack_v1.json","capability_id":"RSI_OMEGA_SKILL_MODEL_GENESIS","cooldown_ticks_u64":5,"enabled":false,"orchestrator_module":"cdel.v18_0.campaign_omega_skill_model_genesis_v1","promotion_bundle_rel":"","risk_class":"LOW","state_dir_rel":"daemon/rsi_omega_skill_model_genesis_v1/state","verifier_module":"cdel.v18_0.verify_rsi_omega_skill_report_v1"},{"budget_cost_hint_q32":{"q":2147483648},"campaign_id":"rsi_model_genesis_v10_0","campaign_pack_rel":"campaigns/rsi_model_genesis_v10_0/rsi_model_genesis_pack_v1.json","capability_id":"RSI_MODEL_GENESIS_V10","cooldown_ticks_u64":25,"enabled":false,"orchestrator_module":"orchestrator.rsi_model_genesis_v10_0","promotion_bundle_rel":"daemon/rsi_model_genesis_v10_0/state/promotion/*.model_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_model_genesis_v10_0/state","verifier_module":"cdel.v10_0.verify_rsi_model_genesis_v1"},{"budget_cost_hint_q32":{"q":4294967296},"campaign_id":"rsi_eudrs_u_train_v1","campaign_pack_rel":"campaigns/rsi_eudrs_u_train_v1/rsi_eudrs_u_train_pack_v1.json","capability_id":"RSI_EUDRS_U_TRAIN","cooldown_ticks_u64":1,"enabled":false,"orchestrator_module":"orchestrator.rsi_eudrs_u_train_v1","promotion_bundle_rel":"daemon/rsi_eudrs_u_train_v1/state/promotion/*.eudrs_u_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_eudrs_u_train_v1/state","verifier_module":"cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1"},{"budget_cost_hint_q32":{"q":4294967296},"campaign_id":"rsi_eudrs_u_index_rebuild_v1","campaign_pack_rel":"campaigns/rsi_eudrs_u_index_rebuild_v1/rsi_eudrs_u_index_rebuild_pack_v1.json","capability_id":"RSI_EUDRS_U_INDEX_REBUILD","cooldown_ticks_u64":1,"enabled":false,"orchestrator_module":"orchestrator.rsi_eudrs_u_index_rebuild_v1","promotion_bundle_rel":"daemon/rsi_eudrs_u_index_rebuild_v1/state/promotion/*.eudrs_u_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_eudrs_u_index_rebuild_v1/state","verifier_module":"cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1"},{"budget_cost_hint_q32":{"q":4294967296},"campaign_id":"rsi_eudrs_u_ontology_update_v1","campaign_pack_rel":"campaigns/rsi_eudrs_u_ontology_update_v1/rsi_eudrs_u_ontology_update_pack_v1.json","capability_id":"RSI_EUDRS_U_ONTOLOGY_UPDATE","cooldown_ticks_u64":1,"enabled":false,"orchestrator_module":"orchestrator.rsi_eudrs_u_ontology_update_v1","promotion_bundle_rel":"daemon/rsi_eudrs_u_ontology_update_v1/state/promotion/*.eudrs_u_promotion_bundle_v1.json","risk_class":"MED","state_dir_rel":"daemon/rsi_eudrs_u_ontology_update_v1/state","verifier_module":"cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1"},{"budget_cost_hint_q32":{"q":4294967296},"campaign_id":"rsi_eudrs_u_eval_cac_v1","campaign_pack_rel":"campaigns/rsi_eudrs_u_eval_cac_v1/rsi_eudrs_u_eval_cac_pack_v1.json","capability_id":"RSI_EUDRS_U_EVAL_CAC","cooldown_ticks_u64":1,"enabled":false,"orchestrator_module":"orchestrator.rsi_eudrs_u_eval_cac_v1","promotion_bundle_rel":"daemon/rsi_eudrs_u_eval_cac_v1/state/promotion/*.eudrs_u_promotion_bundle_v1.json","risk_class":"LOW","state_dir_rel":"daemon/rsi_eudrs_u_eval_cac_v1/state","verifier_module":"cdel.v18_0.eudrs_u.verify_eudrs_u_run_v1"}],"schema_version":"omega_capability_registry_v2"}```

### 3.2 Active utility policy used by promoter in this run

Resolved via pack/profile chain:
- Pack: `campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json`
- Profile: `campaigns/rsi_omega_daemon_v19_0_long_run_v1/long_run_profile_v1.json`
- Utility policy relpath in profile: `utility/omega_utility_policy_v1.json`
- Final path: `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json`

SHA-256: `3080cf02199e7fd27ed7bf22661c1f365c4b053cc3074bb4011080d12a97c162`

```json
{"declared_class_by_capability":{"RSI_EPISTEMIC_REDUCE_V1":"CANARY_HEAVY","RSI_EUDRS_U_TRAIN":"BASELINE_CORE","RSI_GE_SH1_OPTIMIZER":"MAINTENANCE","RSI_KNOWLEDGE_TRANSPILER":"FRONTIER_HEAVY","RSI_OMEGA_NATIVE_MODULE":"FRONTIER_HEAVY","RSI_POLYMATH_BOOTSTRAP_DOMAIN":"BASELINE_CORE","RSI_POLYMATH_CONQUER_DOMAIN":"BASELINE_CORE","RSI_POLYMATH_SCOUT":"BASELINE_CORE","RSI_POLYMATH_SIP_INGESTION_L0":"CANARY_HEAVY","RSI_SAS_CODE":"BASELINE_CORE","RSI_SAS_METASEARCH":"BASELINE_CORE","RSI_SAS_SCIENCE":"BASELINE_CORE"},"heavy_policies":{"RSI_EPISTEMIC_REDUCE_V1":{"policy_artifact_relpath":"epistemic_reduce_stress_receipt_v1.json","primary_signal":"NONTRIVIAL_DELTA","primary_threshold_u64":1,"probe_suite_id":"epistemic_reduce_probe_suite_v1","stress_probe_suite_id":"epistemic_reduce_stress_suite_v1","stress_signal":"REQUIRE_POLICY_ARTIFACT","stress_threshold_u64":1},"RSI_KNOWLEDGE_TRANSPILER":{"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"probe_suite_id":"omega_transpiler_probe_suite_v1","stress_probe_suite_id":"omega_transpiler_stress_suite_v1","stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"RSI_OMEGA_NATIVE_MODULE":{"primary_signal":"WORK_UNITS_REDUCTION","primary_threshold_u64":10,"probe_suite_id":"omega_native_swap_probe_suite_v1","stress_probe_suite_id":"omega_native_stress_probe_suite_v1","stress_signal":"REQUIRE_HEALTHCHECK_HASH","stress_threshold_u64":1},"RSI_POLYMATH_SIP_INGESTION_L0":{"primary_signal":"NONTRIVIAL_DELTA","primary_threshold_u64":1,"probe_suite_id":"polymath_sip_probe_suite_v1","stress_probe_suite_id":"polymath_sip_stress_suite_v1","stress_signal":"REQUIRE_PATCH_DELTA","stress_threshold_u64":1}},"policy_id":"sha256:b57fc0cbc5310e8002ebd7007a91e324db5ee83ee90d09ff66a9d845f935ec61","runtime_stats_source_id":"omega_native_router_kernel_counter_v1","schema_name":"utility_policy_v1","schema_version":"v19_0"}
```

### 3.3 Long-run profile used by this run

Path: `campaigns/rsi_omega_daemon_v19_0_long_run_v1/long_run_profile_v1.json`

SHA-256: `79b772a95953a88f2653cb2a25f10b0a09dfd728395140eb91c2050c7a191166`

```json
{"anti_monopoly":{"consecutive_no_output_limit_u64":50,"cooldown_for_ticks_u64":50,"low_diversity_campaign_limit_u64":3,"window_ticks_u64":50},"dependency_debt":{"debt_limit_u64":3,"max_ticks_without_frontier_attempt_u64":50},"evaluation":{"ek_rel":"eval/ek_omega_v18_0_v2.json","eval_every_ticks_u64":50,"mode":"CLASSIFY_ONLY","suite_rel":"eval/omega_math_science_task_suite_v1.json"},"frontier_health_gate":{"max_budget_exhaust_u64":0,"max_invalid_u64":0,"max_route_disabled_u64":0,"window_ticks_u64":100},"lane_cadence":{"canary_every_ticks_u64":10,"frontier_every_ticks_u64":100},"lanes":{"baseline_capability_ids":["RSI_SAS_CODE","RSI_SAS_METASEARCH","RSI_SAS_SCIENCE","RSI_GE_SH1_OPTIMIZER","RSI_POLYMATH_SCOUT","RSI_POLYMATH_BOOTSTRAP_DOMAIN","RSI_POLYMATH_CONQUER_DOMAIN","RSI_EUDRS_U_TRAIN","RSI_OMEGA_NATIVE_MODULE","RSI_KNOWLEDGE_TRANSPILER"],"canary_capability_ids":["RSI_SAS_CODE","RSI_SAS_METASEARCH","RSI_SAS_SCIENCE","RSI_EPISTEMIC_REDUCE_V1","RSI_POLYMATH_SIP_INGESTION_L0"],"frontier_capability_ids":["RSI_OMEGA_NATIVE_MODULE","RSI_KNOWLEDGE_TRANSPILER","RSI_EPISTEMIC_REDUCE_V1","RSI_POLYMATH_SIP_INGESTION_L0"]},"loop_breaker_scope_mode":"RESET_ON_LAUNCH","mission":{"default_priority":"MED","max_injected_goals_u64":8,"mission_request_rel":"configs/mission_request_v1.json"},"profile_id":"sha256:4f9483a8cc30580b3cbe2115b25a0eda036b6e747001c337e3e580795a7c1895","schema_name":"long_run_profile_v1","schema_version":"v19_0","utility_policy_id":"sha256:b57fc0cbc5310e8002ebd7007a91e324db5ee83ee90d09ff66a9d845f935ec61","utility_policy_rel":"utility/omega_utility_policy_v1.json"}
```

---

## 4) Probe Presence and How Probes Are Loaded

### 4.1 Probe registry file(s) and load chain

Effective source of probe IDs/policies in this run:
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json`

Schema that defines optional probe registry section:
- `Genesis/schema/v19_0/utility_policy_v1.jsonschema`

`probe_registry_v1` presence check in active policy:

```json
{
  "has_probe_registry_v1": false,
  "heavy_policy_probe_suite_ids": [
    {
      "capability_id": "RSI_EPISTEMIC_REDUCE_V1",
      "probe_suite_id": "epistemic_reduce_probe_suite_v1",
      "stress_probe_suite_id": "epistemic_reduce_stress_suite_v1"
    },
    {
      "capability_id": "RSI_KNOWLEDGE_TRANSPILER",
      "probe_suite_id": "omega_transpiler_probe_suite_v1",
      "stress_probe_suite_id": "omega_transpiler_stress_suite_v1"
    },
    {
      "capability_id": "RSI_OMEGA_NATIVE_MODULE",
      "probe_suite_id": "omega_native_swap_probe_suite_v1",
      "stress_probe_suite_id": "omega_native_stress_probe_suite_v1"
    },
    {
      "capability_id": "RSI_POLYMATH_SIP_INGESTION_L0",
      "probe_suite_id": "polymath_sip_probe_suite_v1",
      "stress_probe_suite_id": "polymath_sip_stress_suite_v1"
    }
  ]
}
```

### 4.2 Code paths proving loading/gating behavior

- Utility policy is loaded and pinned:
  - `orchestrator/omega_v19_0/microkernel_v1.py:1483`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:864`

- Probe registry is taken from `utility_policy.probe_registry_v1`:
  - `orchestrator/omega_v19_0/microkernel_v1.py:1524`

- Required probe IDs for capability come from heavy policy (`required_probe_ids_v1` or fallback to `probe_suite_id` + `stress_probe_suite_id`):
  - `orchestrator/omega_v19_0/microkernel_v1.py:1550`

- Heavy lane gate fails on missing probe IDs/assets:
  - `orchestrator/omega_v19_0/microkernel_v1.py:1586`
  - `orchestrator/omega_v19_0/microkernel_v1.py:1615`

- Plan rewrite/drop reason when probe coverage gate fails:
  - `orchestrator/omega_v19_0/microkernel_v1.py:6098`
  - `orchestrator/omega_v19_0/microkernel_v1.py:6139`

### 4.3 One passing probe receipt (known-good capability)

Path: `runs/p13_canary_off_60/tick_000059/daemon/rsi_omega_daemon_v19_0/state/dispatch/06367e310ea0aef1/promotion/sha256_76293582857cd897118a4516cc5786457b25a52f8662519ce59d9d0ba333c937.utility_proof_receipt_v1.json`

```json
{"baseline_ref_hash":"sha256:844bc38b60c7684e29c3f88950942a7634065eab3ba18d070bafc45ba970f417","candidate_bundle_hash":"sha256:a75557038a11dd062d7144afc8fc25f3705ebf243cfbcf22f44d861dd8762f16","candidate_bundle_present_b":true,"capability_id":"RSI_GE_SH1_OPTIMIZER","correctness_ok_b":true,"declared_class":"MAINTENANCE","effect_class":"EFFECT_MAINTENANCE_OK","primary_probe":{"input_hash":"sha256:4db6578ca0a17b31c18931bdad3585c25a52da7930da5c71d338f3ee91411dcd","output_hash":"sha256:556e11c719c4a030811af93dd51d9885af2eeb49e500f98421510174286a20f4"},"probe_executed_b":true,"probe_suite_id":"utility_probe_suite_default_v1","reason_code":"UTILITY_OK","receipt_id":"sha256:abd30218382de33a053fcb8afb3617682767dcd318d05a7b8a76326b9d69fed8","runtime_stats_hash":null,"runtime_stats_source_id":"omega_native_router_kernel_counter_v1","schema_name":"utility_proof_receipt_v1","schema_version":"v19_0","signal_a_ok_b":true,"signal_b_ok_b":true,"stress_probe":{"input_hash":"sha256:cf27ecc9faf22dc9077d1a33bcf8673e1d3050ce1dc63cf283760725ddf02569","output_hash":"sha256:0ffb28eb956d19912943a8a8e6865cafb99dd9602ef334d03e677680c74c619c"},"stress_probe_suite_id":"utility_stress_probe_suite_default_v1","tick_u64":59,"utility_metrics":{"baseline_work_units_u64":null,"binary_artifact_delta_present_b":false,"hard_task_any_gain_b":false,"hard_task_baseline_init_b":false,"hard_task_code_correctness_delta_q32":0,"hard_task_delta_q32":0,"hard_task_gain_count_u64":0,"hard_task_gate_ok_b":true,"hard_task_observation_hash":"sha256:9b088967af6a8dfad1e77dc15b5d31a25320c4ba8e201719f6c495039a6ddfcd","hard_task_performance_delta_q32":0,"hard_task_prev_score_q32":858993459,"hard_task_previous_observation_hash":null,"hard_task_reasoning_delta_q32":0,"hard_task_suite_score_delta_q32":0,"j_delta_q32_i64":0,"non_ws_non_comment_delta_u64":2,"predicted_hard_task_baseline_score_q32":0,"predicted_hard_task_delta_q32":0,"predicted_hard_task_patched_score_q32":0,"runtime_stats_source_match_b":true,"runtime_total_work_units_u64":0},"utility_ok_b":true,"utility_thresholds":{"hard_task_min_gain_count_u64":1,"primary_signal":"NONTRIVIAL_DELTA","primary_threshold_u64":1,"require_hard_task_gain_b":true,"stress_signal":"REQUIRE_PATCH_DELTA","stress_threshold_u64":1}}
```

---

## 5) Hard-Task Metric Definition and Dependency Chain

### 5.1 Where `hard_task_score_q32` / `hard_task_delta_q32` are computed

#### Observer metric computation site

Path: `CDEL-v2/cdel/v18_0/omega_observer_v1.py`

- Hard-task suite run + metric extraction + baseline delta vs previous observation:
  - `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1064`
  - `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1088`
  - `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1148`
  - `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1150`

Key logic excerpt:

```python
hard_task_suite_v1 = evaluate_hard_task_suite_v1(repo_root=root)
hard_task_metric_q32_by_id = hard_task_metric_q32_by_id_from_suite(suite_eval=hard_task_suite_v1)
hard_task_suite_score_q32 = int(hard_task_metric_q32_by_id.get(_HARD_TASK_METRIC_IDS[3], 0))
hard_task_score_q32 = int(hard_task_suite_score_q32)
...
previous_hard_task_score_q32 = int(_metric_q32(prev_metrics, "hard_task_score_q32"))
hard_task_delta_q32 = int(hard_task_score_q32) - int(previous_hard_task_score_q32)
```

#### Eval cadence emission site

Path: `orchestrator/omega_v19_0/eval_cadence_v1.py`

- Emission cadence and report build:
  - `orchestrator/omega_v19_0/microkernel_v1.py:5087`
  - `orchestrator/omega_v19_0/microkernel_v1.py:5103`

- Hard-task aggregation in eval report:
  - `orchestrator/omega_v19_0/eval_cadence_v1.py:78`
  - `orchestrator/omega_v19_0/eval_cadence_v1.py:82`
  - `orchestrator/omega_v19_0/eval_cadence_v1.py:123`

Key logic excerpt:

```python
hard_task_score_q32 = int(_metric_q32(observation_report, "hard_task_suite_score_q32"))
hard_task_delta_q32 = 0
if isinstance(previous_observation_report, dict):
    for metric_id in _HARD_TASK_METRIC_IDS:
        hard_task_delta_q32 += int(_metric_q32(observation_report, metric_id)) - int(
            _metric_q32(previous_observation_report, metric_id)
        )
```

#### Utility gate in promoter

Path: `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`

- Reads latest + previous observation artifacts to derive hard-task deltas:
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1205`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1223`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1271`

- Utility hard-task gate:
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1744`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1767`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1817`

Key logic excerpt:

```python
hard_task_observation = _hard_task_observation_deltas(dispatch_ctx)
...
hard_task_any_gain_b = (not hard_task_baseline_init_b) and (
    int(hard_task_gain_count_u64) >= int(hard_task_required_gain_count_u64)
)
...
if require_hard_task_gain_b:
    hard_task_ok_b = bool(hard_task_any_gain_b)
    utility_ok_b = bool(utility_ok_b and hard_task_ok_b)
```

### 5.2 Baseline storage/read dependency chain

- Baseline emitted into observation metrics each tick:
  - `hard_task_prev_score_q32`
  - `hard_task_baseline_init_u64`
  - `hard_task_delta_q32`
  - `hard_task_gain_count_u64`
  - See `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1149` to `CDEL-v2/cdel/v18_0/omega_observer_v1.py:1152`

- Promoter reads observation artifacts from `state/observations/sha256_*.omega_observation_report_v1.json` and computes deltas:
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1218`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1248`
  - `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1277`

- Eval cadence also computes report-level hard-task deltas from current/previous observations:
  - `orchestrator/omega_v19_0/eval_cadence_v1.py:80`

---

## 6) Provenance (backend/model) for one forcing-off run

Run: `runs/p13_canary_off_60`

From `runs/p13_canary_off_60/run_env_receipt_v1.json`:

- `resolved_orch_llm_backend`: `mlx`
- `resolved_orch_model_id`: `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`

(These same values are also present in `runs/p13_canary_off_60/configs/long_run_launch_manifest_v1.json`.)

---

## Appendix: Quick File Integrity Fingerprints

- `runs/p13_canary_off_60/run_env_receipt_v1.json` -> `sha256:1bcd49ee14cb8133fb1ff5f6f5872cc4de43e3a6842730e87c420c56e6206f73`
- `runs/p13_canary_off_60/configs/long_run_launch_manifest_v1.json` -> `sha256:5122ed02fad233d3ed2945ba4144e2610021f488f601900b9562605a6093ce38`
- `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json` -> `sha256:c4d7a7bbb3f7c72e81cc4313eece5d518f6a78a00096216940af9b437e62c4e1`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/utility/omega_utility_policy_v1.json` -> `sha256:3080cf02199e7fd27ed7bf22661c1f365c4b053cc3074bb4011080d12a97c162`
- `campaigns/rsi_omega_daemon_v19_0_long_run_v1/long_run_profile_v1.json` -> `sha256:79b772a95953a88f2653cb2a25f10b0a09dfd728395140eb91c2050c7a191166`
- `runs/p14_micro_canary_15/tick_000002/.../sha256_ec0becb4e439da2f480a9c40a9358adffb571c36605949fd1f1384e80f519bc8.ccap_receipt_v1.json` -> `sha256:b92232c494326f924c5496e89be510b812e7097547643bef753f6a7a4f8422d0`

