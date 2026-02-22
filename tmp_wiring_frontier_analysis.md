# WIRING_CLASS_REQUIRED + Frontier Attempt Analysis

## 1) Code locations that emit `WIRING_CLASS_REQUIRED` and mark attempts invalid/rejected

### A. Emit threshold code `WIRING_CLASS_REQUIRED`
- `CDEL-v2/cdel/v19_0/nontriviality_cert_v1.py:44`
  - Defines `THRESHOLD_FAIL_WIRING_CLASS_REQUIRED = "WIRING_CLASS_REQUIRED"`.
- `CDEL-v2/cdel/v19_0/nontriviality_cert_v1.py:330`
  - `evaluate_wiring_class(...)` computes wiring evidence.
- `CDEL-v2/cdel/v19_0/nontriviality_cert_v1.py:357`
  - Returns `False, THRESHOLD_FAIL_WIRING_CLASS_REQUIRED` when no accepted wiring evidence is found.
- `CDEL-v2/cdel/v19_0/nontriviality_cert_v1.py:472`
  - `build_nontriviality_cert_v1(...)` stores this into cert field `failed_threshold_code` and sets `wiring_class_ok_b`.

### B. Precheck-level rejection/drop (candidate not sent to CCAP in forced-heavy mode)
- `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py:2442`
- `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py:2452`
  - If `forced_heavy_b` and `nontriviality_cert_v1.wiring_class_ok_b == false`, candidate row is written with:
  - `precheck_decision_code = "DROPPED_INSUFFICIENT_WIRING_DELTA"`
  - `selected_for_ccap_b = false`

### C. Subverifier-level invalidation (attempt marked invalid)
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1265`
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py:1270`
  - For SH1 capability, promoter rewrites subverifier result to:
  - `status = "INVALID"`
  - `reason_code = "VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA"`
  - Includes `nontriviality_cert_v1` evidence (contains `failed_threshold_code: WIRING_CLASS_REQUIRED` when applicable).

### D. Verifier consistency check for precheck decisions
- `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py:2015`
- `CDEL-v2/cdel/v19_0/verify_rsi_omega_daemon_v1.py:2019`
  - Enforces determinism: for `DROPPED_INSUFFICIENT_WIRING_DELTA`, cert must reflect failed wiring (`wiring_class_ok_b` cannot be true unless archetype explicitly failed).

---

## 2) Patch/candidate schema fields where wiring class appears

### Candidate precheck schema
- `Genesis/schema/v19_0/candidate_precheck_receipt_v1.jsonschema:107`
  - Candidate row contains `nontriviality_cert_v1`.
- `Genesis/schema/v19_0/candidate_precheck_receipt_v1.jsonschema:129`
  - Required field: `wiring_class_ok_b`.
- `Genesis/schema/v19_0/candidate_precheck_receipt_v1.jsonschema:176`
  - Required field: `failed_threshold_code`.
- `Genesis/schema/v19_0/candidate_precheck_receipt_v1.jsonschema:84`
  - Candidate decision enum includes `DROPPED_INSUFFICIENT_WIRING_DELTA`.

### Subverifier receipt schema
- `Genesis/schema/v18_0/omega_subverifier_receipt_v1.jsonschema:66`
  - Receipt contains optional `nontriviality_cert_v1`.
- `Genesis/schema/v18_0/omega_subverifier_receipt_v1.jsonschema:88`
  - Required nested field: `wiring_class_ok_b`.
- `Genesis/schema/v18_0/omega_subverifier_receipt_v1.jsonschema:138`
  - Required nested field: `failed_threshold_code`.

---

## 3) Example attempt directory + receipts (precheck + decision + verifier result)

### Attempt directory (concrete run)
- Base dispatch directory:
  - `runs/premarathon_probe_step5_v2/tick_000003/daemon/rsi_omega_daemon_v19_0/state/dispatch/ec34af4b6bab8275/`
- Subrun directory:
  - `runs/premarathon_probe_step5_v2/tick_000003/daemon/rsi_omega_daemon_v19_0/state/subruns/ec34af4b6bab8275_rsi_ge_symbiotic_optimizer_sh1_v0_1/`

### Decision receipt
- Path:
  - `runs/premarathon_probe_step5_v2/tick_000003/daemon/rsi_omega_daemon_v19_0/state/decisions/sha256_5c86ffd76d29941d7c4c9f7075b4fc95cbbee8f9bc95ffd90f97d389bc4a88de.omega_decision_plan_v1.json`
- Key fields:
```json
{
  "schema_version": "omega_decision_plan_v1",
  "tick_u64": 3,
  "action_kind": "RUN_CAMPAIGN",
  "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
  "capability_id": "RSI_GE_SH1_OPTIMIZER"
}
```

### Candidate precheck receipt
- Path:
  - `runs/premarathon_probe_step5_v2/tick_000003/daemon/rsi_omega_daemon_v19_0/state/subruns/ec34af4b6bab8275_rsi_ge_symbiotic_optimizer_sh1_v0_1/precheck/sha256_46496db7097bb61e162eef4265a802e7142c8b91ab479a5e14d1fe4cbc96c44c.candidate_precheck_receipt_v1.json`
- Key fields:
```json
{
  "schema_name": "candidate_precheck_receipt_v1",
  "schema_version": "v19_0",
  "tick_u64": 3,
  "precheck_status_code": "OK",
  "dispatch_happened_b": true,
  "candidate_count_u32": 1,
  "candidates": [
    {
      "template_id": "JSON_TWEAK_BUDGET_HINT",
      "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
      "precheck_decision_code": "SELECTED_FOR_CCAP",
      "selected_for_ccap_b": true,
      "patch_sha256": "sha256:e9b194ece2617b5258420052d8c442378ddc03308ff79072f6d78e2c861c169f",
      "ccap_id": "sha256:fd78f7f2a50b4709bebdc045ed291d6daa24451ed622b4e63e432846f7b788fd",
      "nontriviality_cert_v1": {
        "wiring_class_ok_b": false,
        "failed_threshold_code": "WIRING_CLASS_REQUIRED",
        "ast_nodes_changed_u32": 0,
        "touched_paths_u32": 1,
        "call_edges_changed_b": false,
        "control_flow_changed_b": false,
        "data_flow_changed_b": false,
        "public_api_changed_b": false,
        "shape_id": "sha256:3a6215805374537ab7943e58d053f4ca2665c240fd4ae4002162268d474ab66c"
      }
    }
  ]
}
```

### Verifier result (subverifier receipt)
- Path:
  - `runs/premarathon_probe_step5_v2/tick_000003/daemon/rsi_omega_daemon_v19_0/state/dispatch/ec34af4b6bab8275/verifier/sha256_c884008dfe88f8e3a577d12f6daaa28518e60343bd742554144947af4de3c965.omega_subverifier_receipt_v1.json`
- Key fields:
```json
{
  "schema_version": "omega_subverifier_receipt_v1",
  "tick_u64": 3,
  "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
  "verifier_module": "cdel.v18_0.verify_ccap_v1",
  "result": {
    "reason_code": "VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA",
    "status": "INVALID"
  },
  "nontriviality_cert_v1": {
    "wiring_class_ok_b": false,
    "failed_threshold_code": "WIRING_CLASS_REQUIRED",
    "shape_id": "sha256:3a6215805374537ab7943e58d053f4ca2665c240fd4ae4002162268d474ab66c",
    "touched_relpaths_v1": [
      "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"
    ],
    "ast_nodes_changed_u32": 0,
    "call_edges_changed_b": false,
    "control_flow_changed_b": false,
    "data_flow_changed_b": false,
    "public_api_changed_b": false
  }
}
```

---

## 4) Logic that sets `frontier_attempt_counted_b` and why it is false (or unset) in this run

### Where it is set
- Initialization:
  - `orchestrator/omega_v19_0/microkernel_v1.py:5600`
  - `frontier_attempt_counted_b = False`
- Set true only when evidence gate passes:
  - `orchestrator/omega_v19_0/microkernel_v1.py:5855`
  - Calls `_frontier_attempt_evidence_satisfied(...)`
  - If true, sets `frontier_attempt_counted_b = True` at `:5863`

### Evidence gate conditions
- `orchestrator/omega_v19_0/microkernel_v1.py:2663`
  - `_frontier_attempt_evidence_satisfied(...)` requires all of:
1. Action kind is `RUN_CAMPAIGN` or `RUN_GOAL_TASK` (`:2672`).
2. Either declared class is heavy or lane is `FRONTIER` (`:2676`).
3. Both `dispatch_receipt` and `subverifier_receipt` exist and validate (`:2678-2681`).
4. Dispatch/subverifier tick and campaign IDs match (`:2682-2689`).
5. Subverifier status is `VALID` or `INVALID` (`:2690-2692`).

### Why not counted in this sampled run
- Run index row (`tick_000003`) shows:
  - `status = "ERROR"`
  - `state_verifier_reason_code = "TICK_PROCESS_ERROR"`
  - `frontier_attempt_counted_b = null`
  - Source: `runs/premarathon_probe_step5_v2/index/long_run_tick_index_v1.jsonl` (line 3).
- Because tick finalization failed, the persisted row does not carry a finalized boolean outcome.
- Operationally, this means the attempt was not credited as a frontier-counted attempt in that run record.
- Even absent the process error, this sample is lane `BASELINE`, so frontier counting would still require heavy declared class evidence path to pass.

