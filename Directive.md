## Directive: SH-1 v0.1 (Continual Novelty & Compounding) — extend SH-0 v0.2 without adding trust or governance

### Hard requirements

* **No new trust**: SH-1 is **GE-side only**. RE2 acceptance remains exactly SH-0 (CCAP→verify_ccap_v1→EK runner→RE2 receipt→promoter).
* **No new governance**: do not add any new “approvals.” Authority remains `authority_pins_v1.json` + existing EK/OP pool allowlists and promotion/activation flow.
* **Determinism**: SH-1 state is derived *only* from RE2 receipts + pinned GE config and must be bit-identical given the same ordered receipt stream.

---

# 0) Pre-req hardening (must be done first)

You have one failing non-CCAP test: `test_goal_done_not_selected_again.py` failing `INVALID:NONDETERMINISTIC` in `verify_rsi_omega_daemon_v1.py` during observation replay comparison.

### 0.1 Root cause (most likely)

Your orchestrator observer is now carrying forward metric series (prev→current), but the verifier recomputation path `_recompute_observation_from_sources(...)` reconstructs `metric_series` as single-element lists, so hashes differ and verification fails.

### 0.2 Fix spec (CDEL-v2)

**File:** `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
**Goal:** When recomputing observation, reproduce the same “series carry-forward” behavior as the observer.

Implement:

1. Add helper:

```python
def _find_prev_observation_report(
    *, state_root: Path, current_tick_u64: int
) -> dict[str, Any] | None:
    # deterministically locate prior observation report (tick_u64 == current_tick-1) if present
```

Deterministic selection rule:

* Scan `state_root / "observations" / "sha256_*.omega_observation_report_v1.json"` in lexicographic order.
* Load each payload; select the one with `tick_u64 == current_tick_u64 - 1`.
* If multiple match (shouldn’t), pick lexicographically smallest file path.
* If none exist, return None.

2. Update `_recompute_observation_from_sources(...)` signature to accept `prev_observation: dict | None`.

3. When building `payload["metric_series"]`:

* If `prev_observation is None`: keep current behavior (single-element lists).
* Else:

  * For each metric series key:

    * Take `prev_series = prev_observation["metric_series"][key]` (must be list; else fail SCHEMA_FAIL)
    * Append the newly computed element deterministically
    * If `len(prev_series) >= MAX_SERIES_LEN_U64` (new constant, default 64), keep the last `MAX_SERIES_LEN_U64-1` then append new.
* Preserve exact key ordering (write series keys in fixed order as currently).

4. In `verify(...)`, before `recomputed_obs = _recompute_observation_from_sources(...)`, load:

```python
prev_obs = _find_prev_observation_report(state_root=state_root, current_tick_u64=int(obs_payload["tick_u64"]))
```

and pass it in.

### 0.3 Regression tests

Add test: `CDEL-v2/cdel/v18_0/tests_omega_daemon/test_observation_series_replay_deterministic_v1.py`

* Run tick 1, then tick 2 with `prev_state_dir`
* Verify both state dirs are VALID
* Assert verifier no longer fails NONDETERMINISTIC

**DoD 0:** `pytest -q CDEL-v2/cdel/v18_0/tests_omega_daemon/test_goal_done_not_selected_again.py` passes.

---

# 1) SH-1 v0.1 deliverables (GE-only compounding + novelty)

## 1.1 New untrusted GE config (content-addressed, not authority)

### Files (AGI-Stack)

* `tools/genesis_engine/config/ge_config_v1.json`
* `tools/genesis_engine/config/ge_config_v1.md` (human summary)

### Schema (Genesis)

Add under `Genesis/schema/v18_0/`:

* `ge_config_v1.jsonschema`
* `ge_audit_report_v1.jsonschema`
* `ge_xs_snapshot_v1.jsonschema`
* `ge_pd_v1.jsonschema`
* `ge_behavior_sig_v1.jsonschema`

These are **untrusted schemas** (tooling only). They do not enter `authority_pins_v1.json`.

### `ge_config_v1` exact fields

```json
{
  "schema_version": "ge_config_v1",
  "ge_config_id": "sha256:000...0",

  "bucket_fracs_q32": {
    "opt_q32": 2576980377,
    "nov_q32": 858993459,
    "grow_q32": 858993459
  },
  "bucket_min_counts": { "opt_u64": 1, "nov_u64": 1, "grow_u64": 1 },

  "receipt_ingest": {
    "max_receipts_u64": 4096,
    "receipt_globs": [
      "**/ccap_receipt_v1.json",
      "**/sha256_*.ccap_receipt_v1.json",
      "**/ccap_refutation_cert_v1.json",
      "**/sha256_*.ccap_refutation_cert_v1.json"
    ]
  },

  "sentinel_mapping": {
    "BUSY_FAIL": ["BUDGET_EXCEEDED"],
    "LOGIC_FAIL": ["EVAL_STAGE_FAIL", "SITE_NOT_FOUND", "PATCH_HASH_MISMATCH"],
    "SAFETY_FAIL": ["NONDETERMINISM_DETECTED", "CANONICALIZATION_MISMATCH", "AUTH_HASH_MISMATCH", "CANON_VERSION_MISMATCH", "EK_ID_NOT_ACTIVE", "OP_POOL_NOT_ACTIVE", "BASE_TREE_MISMATCH"],
    "OK": []
  },

  "hard_avoid": {
    "enabled_b": true,
    "refutation_codes": ["NONDETERMINISM_DETECTED", "CANONICALIZATION_MISMATCH"],
    "pd_projection": { "touched_paths_prefix_hex_u8": 8 }
  },

  "novelty": {
    "enabled_b": true,
    "reservoir_size_u64": 512,
    "min_novelty_bits_u64": 24
  },

  "proposal_space_patch": {
    "allowed_target_relpaths": [
      "tools/omega/omega_benchmark_suite_v1.py",
      "tools/omega/omega_overnight_runner_v1.py",
      "orchestrator/omega_v18_0/decider_v1.py"
    ],
    "templates": [
      { "template_id": "COMMENT_APPEND", "bucket": "opt" },
      { "template_id": "COMMENT_APPEND", "bucket": "nov" },
      { "template_id": "COMMENT_APPEND", "bucket": "grow" }
    ],
    "size_buckets_bytes_u64": [256, 1024, 4096, 16384, 65536]
  },

  "kpi": {
    "burn_in_receipts_u64": 64,
    "plateau_windows_u64": 10,
    "novelty_min_coverage_q32": 429496729
  }
}
```

**Rules**

* `ge_config_id` = sha256(canonical JSON of config with `ge_config_id` set to zero). Tool fills it.
* Fractions must sum to `2^32` exactly; else SCHEMA_FAIL.

---

## 1.2 Proposal Descriptor (PD) + Experience Store snapshot (XS)

### New module (AGI-Stack)

* `tools/genesis_engine/sh1_pd_v1.py`
* `tools/genesis_engine/sh1_xs_v1.py`

### PD schema (`ge_pd_v1`)

```json
{
  "schema_version": "ge_pd_v1",
  "pd_id": "sha256:000...0",
  "kind": "PATCH",
  "base_tree_id": "sha256:...",
  "ek_id": "sha256:...",
  "op_pool_id": "sha256:...",
  "touched_paths_hash": "sha256:...",
  "size_bucket_u8": 0
}
```

### PD extraction (PATCH kind, exact)

Input: patch bytes from the CCAP bundle.

1. Parse unified diff headers:

* For each file section, record the `b/<relpath>` from `+++ b/<relpath>` (ignore `a/`).
* Collect unique relpaths, reject absolute paths and any `..`.

2. `touched_paths_hash = sha256(canon_json({"paths":[sorted_paths]}))`

3. `size_bucket_u8`:

* Let `n = len(patch_bytes)`.
* Bucket index is the first threshold `t` where `n <= t`; else bucket = `len(thresholds)`.

4. PD canonical bytes:

* canonical JSON with keys in fixed order:
  `schema_version, kind, base_tree_id, ek_id, op_pool_id, touched_paths_hash, size_bucket_u8`
* `pd_id = sha256(Can(PD_without_pd_id))`

### XS snapshot schema (`ge_xs_snapshot_v1`)

```json
{
  "schema_version": "ge_xs_snapshot_v1",
  "xs_id": "sha256:000...0",
  "ge_config_id": "sha256:...",
  "authority_pins_hash": "sha256:...",
  "receipt_stream_hash": "sha256:...",

  "pd_rows": [
    {
      "pd_id": "sha256:...",
      "seen_u64": 0,
      "promote_u64": 0,
      "reject_u64": 0,
      "busy_fail_u64": 0,
      "logic_fail_u64": 0,
      "safety_fail_u64": 0,
      "cost_cpu_ms_u64": 0,
      "cost_wall_ms_u64": 0,
      "mean_yield_q32": 0
    }
  ],

  "hard_avoid_set": [
    {
      "refutation_code": "NONDETERMINISM_DETECTED",
      "touched_paths_hash_prefix_hex": "deadbeef"
    }
  ]
}
```

### XS determinism invariant (SH-1-D1)

Given:

* same `ge_config_id`,
* same `authority_pins_hash`,
* same ordered receipt stream (defined below),
  the resulting `ge_xs_snapshot_v1.json` must be byte-identical.

### Receipt stream ordering (exact)

Ingest receipts by scanning `recent_runs_root`:

* Collect all matching receipt files from config globs.
* Sort by `path.as_posix()`.
* For each `ccap_receipt_v1`, look for a sibling/nearby `ccap_refutation_cert_v1` with same `ccap_id` if present (else none).
* Build a canonical list of per-ccap “experience events” in this sorted order.

Define `receipt_stream_hash = sha256(canon_json({"events":[{ccap_id, receipt_hash, refutation_code_or_empty}...]}))`

---

## 1.3 Behavior Signature φ(r) and novelty

### Module (AGI-Stack)

* `tools/genesis_engine/sh1_behavior_sig_v1.py`

### Behavior signature schema (`ge_behavior_sig_v1`)

```json
{
  "schema_version": "ge_behavior_sig_v1",
  "beh_id": "sha256:000...0",
  "phi": [0,0,0,0,0,0,0,0]
}
```

### φ extraction (exact, receipt-only)

From `ccap_receipt_v1` + optional refutation:

* `phi[0]`: decision → PROMOTE=1 else 0
* `phi[1]`: eval_status → PASS=1, FAIL=0, REFUTED=-1
* `phi[2]`: determinism_check → PASS=1, DIVERGED=-1, REFUTED=-2
* `phi[3]`: sentinel class → OK=0, BUSY=1, LOGIC=2, SAFETY=3
* `phi[4]`: cpu_ms bucket (same thresholds as config but on cpu_ms)
* `phi[5]`: wall_ms bucket
* `phi[6]`: refutation_code_hash16 (int from first 2 bytes of sha256(refutation_code UTF-8), or 0 if none)
* `phi[7]`: reserved = 0 (future)

`beh_id = sha256(canon_json({"phi":phi}))`

### Novelty score (exact)

Distance = Hamming distance between 256-bit `beh_id` digests.

For a candidate evaluated at time t:

* reservoir = last `reservoir_size_u64` beh_ids in chronological receipt-stream order
* novelty_bits = min_hamming(beh_id, each in reservoir), or 256 if reservoir empty

Novelty threshold pass if `novelty_bits >= min_novelty_bits_u64`.

**Novelty laundering block (must enforce):**

* novelty must depend only on `beh_id` computed from receipts, never patch size or touched paths.

---

# 2) SH-1 optimizer: GE v0.3 (receipt-driven bucketed proposer)

## 2.1 New tool file

**AGI-Stack**

* `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`
* Keep `v0_2` unchanged for baseline.

## 2.2 CLI (exact)

```bash
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --subrun_out_dir <abs> \
  --ge_config_path tools/genesis_engine/config/ge_config_v1.json \
  --authority_pins_path authority/authority_pins_v1.json \
  --recent_runs_root <abs|empty> \
  --ge_state_root <abs|empty> \
  --seed <u64> \
  --model_id <string> \
  --max_ccaps <1..8>
```

Resolution rules:

* `ge_state_root` uses:

  1. `--ge_state_root` if provided
  2. env `OMEGA_GE_STATE_ROOT` if set
  3. default `<repo_root>/.omega_cache/genesis_engine`

## 2.3 Outputs (exact)

Under `subrun_out_dir/`:

* `ge_run_inputs_fingerprint_v2.json`
* `ge_prompt_response_hashes_v1.json` (if llm_trace present in config or strategy)
* `ge_xs_snapshot_v1.json` (current snapshot after ingest)
* `ge_symbiotic_optimizer_summary_v0_3.json`
* `ccap/sha256_<ccaphex>.ccap_v1.json`
* `ccap/blobs/sha256_<patchhex>.patch`
* (optional) `ccap/refutations/...` not produced by GE

### Fingerprint v2 (exact)

```json
{
  "schema_version": "ge_run_inputs_fingerprint_v2",
  "inputs_hash": "sha256:...",
  "seed": 7,
  "model_id": "ge-v0_3",
  "prompt_hashes": ["sha256:..."],
  "ge_config_id": "sha256:...",
  "authority_pins_hash": "sha256:...",
  "receipt_stream_hash": "sha256:...",
  "xs_id": "sha256:..."
}
```

`inputs_hash = sha256(canon_json(fingerprint_inputs))` where fingerprint_inputs includes all fields above except `inputs_hash`.

### Summary v0.3 (exact)

```json
{
  "schema_version": "ge_symbiotic_optimizer_summary_v0_3",
  "inputs_hash": "sha256:...",
  "auth_hash": "sha256:...",
  "ge_config_id": "sha256:...",
  "bucket_plan": { "opt_u64": 0, "nov_u64": 0, "grow_u64": 0 },
  "ccaps": [
    {
      "bucket": "opt|nov|grow",
      "ccap_id": "sha256:...",
      "ccap_relpath": "ccap/sha256_....ccap_v1.json",
      "patch_blob_id": "sha256:...",
      "patch_relpath": "ccap/blobs/sha256_....patch",
      "target_relpath": "tools/omega/omega_benchmark_suite_v1.py",
      "pd_id": "sha256:..."
    }
  ]
}
```

## 2.4 Bucket scheduler (non-fungible, exact)

Let `N = max_ccaps`.

Compute provisional counts:

* `n_opt = floor(N * opt_q32 / 2^32)`
* `n_nov = floor(N * nov_q32 / 2^32)`
* `n_grow = floor(N * grow_q32 / 2^32)`
  Then distribute remainder (`N - (n_opt+n_nov+n_grow)`) to buckets in deterministic order: `opt, nov, grow`.

Enforce minimum counts:

* If `N >= 3`: ensure each bucket has at least configured min; if a bucket underflows, steal from `opt` first, then `nov`, deterministically.
* If `N < 3`: allocate in order `opt`, then `nov`.

**Non-fungibility rule:** if a bucket has no eligible candidate, it emits fewer proposals; do not reallocate its unused slots.

## 2.5 Candidate selection rules (PATCH only for v0.3)

Create a candidate set from `ge_config.proposal_space_patch.allowed_target_relpaths`.

For each bucket:

* **opt**: choose targets with highest `mean_yield_q32` from XS (tie-break: lowest `seen_u64`, then lexicographic relpath)
* **nov**: choose targets with lowest `seen_u64` (tie-break: lexicographic relpath)
* **grow**: choose targets with highest `busy_fail_u64` rate (tie-break: highest `cost_wall_ms_u64`, then lexicographic)

### Hard Avoid enforcement (HAS)

If enabled:

* If a prior receipt has refutation_code in `hard_avoid.refutation_codes` and its PD touched_paths_hash prefix matches a candidate’s touched_paths_hash prefix length, that candidate is ineligible.

HAS is derived deterministically from the ingested receipt stream and written into `ge_xs_snapshot_v1.json`.

---

# 3) Audit tool (derived only from receipts; falsification metrics)

## 3.1 New tool

**AGI-Stack**

* `tools/genesis_engine/ge_audit_report_sh1_v0_1.py`

## 3.2 CLI (exact)

```bash
python3 tools/genesis_engine/ge_audit_report_sh1_v0_1.py \
  --runs_root <abs> \
  --ge_config_path tools/genesis_engine/config/ge_config_v1.json \
  --out_json <abs>/GE_AUDIT_REPORT_v1.json \
  --out_md <abs>/GE_AUDIT_REPORT.md
```

## 3.3 Output schema (`ge_audit_report_v1`)

```json
{
  "schema_version": "ge_audit_report_v1",
  "ge_config_id": "sha256:...",
  "authority_pins_hash": "sha256:...",
  "receipt_stream_hash": "sha256:...",

  "kpi": {
    "promote_u64": 0,
    "total_wall_ms_u64": 0,
    "yield_promotions_per_wall_ms_q32": 0
  },

  "sentinel_mix": {
    "busy_fail_u64": 0,
    "logic_fail_u64": 0,
    "safety_fail_u64": 0,
    "ok_u64": 0
  },

  "novelty": {
    "reservoir_size_u64": 512,
    "min_novelty_bits_u64": 24,
    "novel_u64": 0,
    "total_u64": 0,
    "novelty_coverage_q32": 0
  },

  "falsification_flags": [
    {"code":"F2_CREATIVITY_COLLAPSE","detail":"..."}
  ]
}
```

KPI computation (exact):

* `promote_u64` = count of `ccap_receipt_v1.decision=="PROMOTE"`
* `total_wall_ms_u64` = sum of `cost_vector.wall_ms`
* `yield_q32 = rat_q32(promote_u64, max(1,total_wall_ms_u64))`

Novelty coverage:

* compute novelty_bits per receipt as above; count those >= threshold.

Falsification triggers implemented as **flags only** (no gating):

* F2 if novelty_coverage_q32 < config threshold for last N receipts (N from config).

---

# 4) Wiring into Omega (optional, staged; keeps governance untouched)

## 4.1 New campaign (CDEL-v2) to run GE v0.3 and emit CCAP promotion bundle

**File (CDEL-v2):**

* `cdel/v18_0/campaign_ge_symbiotic_optimizer_sh1_v0_1.py`

Behavior:

* Run `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py` with:

  * `--subrun_out_dir out_dir`
  * `--recent_runs_root` = parent runs root (if available)
  * `--ge_state_root` from env `OMEGA_GE_STATE_ROOT` (optional)
  * `--max_ccaps 1` initially
* Read `ge_symbiotic_optimizer_summary_v0_3.json`
* For each emitted ccap (initially 1):

  * write promotion bundle:

    * path: `promotion/sha256_<bundle>.omega_promotion_bundle_ccap_v1.json`
    * fields: `schema_version`, `ccap_id`, `ccap_relpath`, `patch_relpath`, `activation_key=ccap_id`, `touched_paths=[ccap_relpath, patch_relpath]`

## 4.2 Capability registry entry (AGI-Stack campaigns)

Add a new capability row (disabled by default) in both:

* `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`
* `campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json`
  (and corresponding `daemon/.../config` copies if you keep duplicated configs)

Entry:

* `capability_id`: `RSI_GE_SH1_OPTIMIZER`
* `campaign_id`: `rsi_ge_symbiotic_optimizer_sh1_v0_1`
* `enabled`: `false` (staged rollout)
* `verifier_module`: `cdel.v18_0.verify_ccap_v1`
* `promotion_bundle_rel`: `"promotion/sha256_*.omega_promotion_bundle_ccap_v1.json"`
* `enable_ccap`: `1`
* Add to appropriate skill family if needed (CODE).

## 4.3 Env propagation for stable GE state root (AGI-Stack)

**File:** `orchestrator/common/run_invoker_v1.py`
Add to `_SANITIZED_ENV_KEYS`:

* `OMEGA_GE_STATE_ROOT`

(If you also rely on polymath store root env, add it here too.)

---

# 5) Tests (must be added)

## 5.1 Fix regression test (pre-req)

* `test_goal_done_not_selected_again.py` passes (after series carry-forward fix).

## 5.2 GE unit/integration tests (AGI-Stack)

Add:

1. `tools/genesis_engine/tests/test_ge_symbiotic_optimizer_v0_3_deterministic.py`

* Run v0.3 twice with same inputs, same recent_runs_root fixture, assert:

  * same `inputs_hash`
  * same `ge_xs_snapshot_v1.json` bytes
  * same CCAP bytes and patch bytes

2. `tools/genesis_engine/tests/test_ge_xs_snapshot_deterministic_v1.py`

* Feed synthetic receipt set (write minimal ccap_receipt_v1 files) in different filesystem mtimes but same lexicographic names; ensure snapshot identical.

3. `tools/genesis_engine/tests/test_ge_bucket_nonfungible_v1.py`

* Set max_ccaps=6; config fractions 0.5/0.3/0.2; assert bucket_plan counts match spec and unused slots do not reallocate.

4. `tools/genesis_engine/tests/test_ge_novelty_laundering_block_v1.py`

* Create two receipts with identical outcomes but different patch sizes; ensure computed novelty bits are equal (since only receipts drive beh_id).

## 5.3 Optional campaign wiring test (CDEL-v2)

* `cdel/v18_0/tests_omega_daemon/test_campaign_ge_sh1_emits_ccap_bundle_v1.py`
* Run the campaign module directly in a temp out_dir; assert promotion bundle exists and touched_paths match `[ccap_relpath, patch_relpath]`.

---

# 6) DoD (acceptance checklist)

### DoD-A: Baseline determinism restored

* Full daemon suite passes:

  * `PYTHONPATH='CDEL-v2:.' pytest -q CDEL-v2/cdel/v18_0/tests_omega_daemon`

### DoD-B: SH-1 core implemented (GE-only)

* `ge_config_v1` exists + validated
* `ge_xs_snapshot_v1.json` produced and deterministic
* bucket scheduler enforced non-fungibly
* novelty metrics computed from receipts only
* `ge_audit_report_sh1_v0_1.py` produces `GE_AUDIT_REPORT_v1.json`

### DoD-C: Optional Omega integration (staged)

* Campaign exists and can emit CCAP promotion bundle
* Capability entry present but **disabled by default**
* When enabled in a dedicated test pack, one CCAP promotion can be verified/promoted end-to-end

---

# 7) Versioning

* SH-0 stays v0.2 (acceptance path unchanged).
* Introduce **SH-1 v0.1** as “GE receipt-driven controller + novelty + KPI audit.”
* Implement GE tool as `ge_symbiotic_optimizer_v0_3.py` (v0.2 kept intact).

---

If you want, paste your annex expansion deltas (anything you changed vs the SH-1 text you provided), and I will align the schema fields and exact file names to match it byte-for-byte.
