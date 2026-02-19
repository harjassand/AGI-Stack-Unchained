# EUDRS-U v1.0 (Unified Hypothesis) - Research Scientist Handoff Pack

**Audience:** research scientist authoring the formal spec for the EUDRS-U v1.0 hypothesis without direct access to this repo checkout.  
**Goal:** remove redundancy by documenting (a) what is *already implemented* in this repository, (b) what is *constrained by trust/determinism/promotion gates*, and (c) exactly where EUDRS-U would integrate (files, artifact contracts, and gating interactions).

This handoff is intentionally repo-anchored: file paths are included so engineering can integrate your spec with minimal translation.

## 1) Snapshot Of This Checkout (Concrete, Repo-Local)

**Repo root:** `AGI-Stack-Clean/`  
**As-of date (local):** 2026-02-13  

### 1.1 Git Coordinates

- Git commit (HEAD): `b59c1fd37d9f9e888c266e539cb69c5c5c260d81`
- Git branch: `fix/unified-4h-ready`

### 1.2 Submodules (Treat As Separate Repos)

The repo uses submodules; changes in these must follow each submodule's conventions.

- `CDEL-v2/` @ `e8f824661e73bc59a9f1fc62e15d3a67f20189f7`
- `Extension-1/` @ `3b7e42209b107c0b29f1ec3c088d26179fe63cd4`
- `Genesis/` @ `8c06bc39d02f8ba22e39685a81bf7e9a30b4c466`
- `agi-orchestrator/` @ `bbc12e93efefe5f08c237e324b2734a2b01c98e4`

### 1.3 Working Tree State (Important For Interpretation)

This checkout is **dirty** and contains large generated artifacts (e.g. `.omega_v18_exec_workspace/`, `runs/`, `.omega_cache/`). These are runtime outputs and should be treated as ephemeral unless a task explicitly targets them.

### 1.4 Capability Registry Reality (Declared vs Enabled)

Capability registries are canonical JSON files used by omega scheduling. In this checkout:

- `campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json`
  - `caps_total = 19`
  - `enabled = 3`: `RSI_SAS_CODE`, `RSI_SAS_METASEARCH`, `RSI_SAS_VAL`
- `campaigns/rsi_omega_daemon_v19_0/omega_capability_registry_v2.json`
  - `caps_total = 20`
  - `enabled = 3`: `RSI_SAS_CODE`, `RSI_SAS_METASEARCH`, `RSI_SAS_VAL`
- `campaigns/rsi_omega_daemon_v19_0_unified/omega_capability_registry_v2.json`
  - `caps_total = 20`
  - `enabled = 7`: base 3 plus `RSI_POLYMATH_{SCOUT,BOOTSTRAP_DOMAIN,CONQUER_DOMAIN}` plus `RSI_GE_SH1_OPTIMIZER`
  - note: `RSI_POLYMATH_SCOUT` and `RSI_GE_SH1_OPTIMIZER` are CCAP-enabled (`enable_ccap: 1`, verifier `cdel.v18_0.verify_ccap_v1`)
- `campaigns/rsi_omega_daemon_v19_0_llm_enabled/omega_capability_registry_v2.json`
  - `caps_total = 20`
  - `enabled = 1`: `RSI_AGI_ORCHESTRATOR_LLM`

These counts matter for your spec when you describe "what runs by default": most declared capabilities are **disabled** unless a specific profile is selected.

## 2) Trust Boundary: What "Authority Unchanged" Means In This Repo

This repo already implements an RE1-RE4 style split. Your EUDRS-U hypothesis explicitly keeps it unchanged; that matches the current acceptance model.

### 2.1 Layers (Repo Reality)

- **RE1 (meta-core):** `meta-core/`
  - Rust kernel verifier: `meta-core/kernel/verifier/`
  - Python wrapper for promotion verification: `meta-core/kernel/verify_promotion_bundle.py`
  - CLI apply/rollback: `meta-core/cli/meta_core_apply.py`, `meta-core/cli/meta_core_rollback.py`
  - Store: `meta-core/store/bundles/`
- **RE2 (verifiers + deterministic runtime):** `CDEL-v2/cdel/`
  - Omega v18 daemon verifier: `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` (1710 LOC in this checkout)
  - CCAP verifier: `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` (793 LOC in this checkout)
  - v19 continuity + axis gates inside RE2: `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`
- **RE3 (proposers):** `Extension-1/` (untrusted proposer layer)
  - Includes self-improvement tooling; treated as untrusted suggestions.
- **RE4 (schemas / canonical formats):** `Genesis/` plus schema directories pinned in RE2
  - RE2 loads v18 schemas from `Genesis/schema/v18_0/` via `CDEL-v2/cdel/v18_0/omega_common_v1.py:schema_dir()`.

### 2.2 Non-Negotiable Acceptance Path (Implemented)

In this repo, durable change occurs only if:

1. **RE2** emits artifacts + verifier receipts and (optionally) a promotion bundle.
2. **RE2**/orchestrator wraps them into a meta-core promotion bundle and passes it to **RE1**.
3. **RE1** verifies fail-closed and, if allowed, applies activation atomically (or simulates in non-live mode).

There is no "out-of-band" acceptance path for code/data changes.

## 3) Determinism Contract (What This Repo Actually Enforces)

Your hypothesis references "DC-1 determinism" with Q32 and strict canonicalization. This repo already has a determinism substrate, but it is scoped to specific artifacts and verifiers.

### 3.1 Canonical JSON: GCJ-1 (Floats Rejected)

Canonicalization is **GCJ-1** in RE2 utilities:

- `CDEL-v2/cdel/v1_7r/canon.py`
  - `canon_bytes()` sorts keys, uses separators `(",", ":")`, writes UTF-8 with trailing newline.
  - **Rejects floats** both on load and on canonicalization (`CanonError("floats are not allowed in canonical json")`).
  - Any artifact written via `write_canon_json()` must contain only: `dict[str, ...]`, `list[...]`, `str`, `bool`, `int`, `null`.

**Implication for EUDRS-U spec:** if you want any "f64" values, they must be encoded as:

- Q32 ints (`{"q": int}`), or
- integers with explicit scaling, or
- strings (only if schema explicitly permits), but not JSON floats.

### 3.2 Q32 Primitives (RE2)

RE2 defines Q32 as a signed 64-bit integer carrier with 32 fractional bits:

- `CDEL-v2/cdel/v18_0/omega_common_v1.py`
  - `Q32_ONE = 1 << 32`
  - `rat_q32(num_u64, den_u64) = (num * Q32_ONE) // den` (integer division)
  - `q32_mul(lhs_q, rhs_q) = (lhs_q * rhs_q) >> 32`
  - `q32_int({"q": int})` is strict: the dict must have *exactly* key set `{"q"}`.

### 3.3 Deterministic Process Invocation (Env Sanitization)

Orchestrator subprocess invocation intentionally captures only a small environment set and forces Python hash determinism:

- `orchestrator/common/run_invoker_v1.py`
  - Sanitized env keys include: `PYTHONHASHSEED`, `PYTHONPATH`, `OMEGA_RUN_SEED_U64`, `OMEGA_NET_LIVE_OK`, `ORCH_LLM_BACKEND`, `ORCH_LLM_REPLAY_PATH`, `ORCH_LLM_LIVE_OK`, etc.
  - Forces `PYTHONHASHSEED = "0"`.
  - Emits an `env_fingerprint_hash` bound to the run record.

### 3.4 Replay Verifier Behavior (Fail-Closed)

The daemon verifier is a replay checker that rejects if any recomputation doesn't match canonical hashes:

- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
  - Recomputes observation from disk sources and checks `canon_hash_obj(recomputed_obs) == canon_hash_obj(claimed_obs)`.
  - Recomputes decision by calling RE2 decider (`cdel.v18_0.omega_decider_v1.decide`) and compares full decision object hash.
  - Recomputes diagnostic issue bundle (`cdel.v18_0.omega_diagnoser_v1.diagnose`) and checks hash.
  - Verifies trace hash-chain tail:
    - `CDEL-v2/cdel/v18_0/omega_trace_hash_chain_v1.py:recompute_head()`
  - Enforces forbidden path policy using allowlists:
    - `CDEL-v2/cdel/v18_0/omega_allowlists_v1.py`
  - Enforces "no absolute paths" recursively on key payloads:
    - `CDEL-v2/cdel/v18_0/omega_common_v1.py:require_no_absolute_paths()`

### 3.5 Tie-Break Paths (Explicit Determinism Proof)

Decision payloads include a `tie_break_path` list and verifiers hash-compare the entire decision object:

- `CDEL-v2/cdel/v18_0/omega_decider_v1.py`
  - Appends explicit strings like:
    - `SAFE_HALT:POLICY_HASH_MISMATCH`
    - `TEMP:LOW|MID|HIGH`
    - `GOAL_SKIP:<goal_id>:DONE|FAILED`
    - `SKIP:<campaign_id>:COOLDOWN|BUDGET|DISABLED`
    - `RUNAWAY_*` markers for runaway mode branches
  - The verifier recomputes `decide()` and checks `canon_hash_obj(recomputed_decision) == canon_hash_obj(claimed_decision)`.

**Implication for EUDRS-U spec:** any "choice" (Top-K, argmax, routing) must emit a comparable deterministic trace fragment so RE2 can replay-check it.

## 4) Omega v18.0: Real Tick Loop (Where Artifacts Actually Come From)

### 4.1 Tick Coordinator (v18)

- `orchestrator/omega_v18_0/coordinator_v1.py`
  - Stages (high-level): freeze pack config, observe, diagnose, decide, dispatch, run subverifier, run promotion, run activation, ledger writes, trace write, snapshot write.
  - Produces canonical artifacts under the selected state/run directory, and references them in the trace hash-chain.

### 4.1.1 Dispatch Execution Model (Workspace, Subruns, Receipts)

The tick coordinator uses RE2's dispatch executor, which is where "subruns as evidence roots" actually come from:

- `CDEL-v2/cdel/v18_0/omega_executor_v1.py:dispatch_campaign()`
  - Builds a deterministic invocation:
    - `PYTHONPATH` is pinned to include: repo root, `CDEL-v2/`, and `Extension-1/agi-orchestrator/`.
    - `OMEGA_TICK_U64` and `OMEGA_RUN_SEED_U64` are passed explicitly.
  - Executes the campaign module via `orchestrator/common/run_invoker_v1.py:run_module()`.
  - Runs in a per-action workspace rooted under:
    - `.omega_v18_exec_workspace/<action_id>_<campaign_id>/`
  - Materializes a persistent subrun under the daemon state root:
    - `state_root/subruns/<action_id>_<campaign_id>/`
    - Materialization is **rename-fastpath** when possible, **copy+delete** on `EXDEV`.
    - Some campaigns force `copy` materialization (`_COPY_MATERIALIZE_CAMPAIGNS` currently includes `rsi_sas_code_v12_0`).
  - Prunes known junk directories under subrun roots (`__pycache__`, `.pytest_cache`, etc).
  - Updates observer indices best-effort:
    - `CDEL-v2/cdel/v18_0/omega_observer_index_v1.py:update_index_from_subrun_best_effort()`
  - Writes an `omega_dispatch_receipt_v1` payload under:
    - `state_root/dispatch/<action_id>/sha256_<...>.omega_dispatch_receipt_v1.json`
    - receipt binds:
      - invoked `py_module`, argv, and `env_fingerprint_hash`
      - `subrun_root_rel` (relative to `state_root`), `state_dir_rel` (campaign's state), and `subrun_tree_hash`
      - stdout/stderr hashes and return code

### 4.2 Observation Sources And Metrics (Verifier Recomputes From Disk)

The verifier binds observation metrics to a list of "sources" with schema IDs and artifact hashes:

- Source suffix map: `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py:_OBS_SOURCE_SUFFIX`
- Fixed-path sources: `...:_OBS_SOURCE_FIXED_PATH_REL`
- Required sources: `...:_OBS_REQUIRED_SOURCE_IDS`

Example RE2 recomputation logic (selected):

- `metasearch_compute_report_v1`: metric is `rat_q32(base_cost, cand_cost_or_1)` (note: this is a *ratio*, not a difference)
- `kernel_hotloop_report_v1`: metric is `rat_q32(top_loop_bytes, sum_bytes_or_1)`
- `sas_system_perf_report_v1`: metric is `rat_q32(cand_cost_total, ref_cost_total_or_1)`
- `sas_science_promotion_bundle_v1`: metric reads `discovery_bundle.heldout_metrics.rmse_pos1_q32.q`

Additionally, the observation recomputation includes derived "system health" metrics such as promotion reject rate, subverifier invalid rate, activation denied rate, and a "brain temperature" Q32 computed by:

- `CDEL-v2/cdel/v18_0/omega_temperature_v1.py:compute_temperature_q32()`

### 4.3 Episodic Memory + Trace Chains (Existing "Root-Hash-Like" Telemetry)

- Trace hash-chain:
  - `CDEL-v2/cdel/v18_0/omega_trace_hash_chain_v1.py`
  - `H0` seed binds: run seed, pack/policy/registry/objectives hashes, tick, prev state hash.
  - Each step re-hashes a `(prev_head, artifact_hash)` pair.
- Episodic memory (sliding window):
  - `CDEL-v2/cdel/v18_0/omega_episodic_memory_v1.py`
  - Maintains last `window_size_u64` (default 256) episodes with normalized outcome + touched families + context hash.

**Relevance to EUDRS-U:** you can reuse this "hash chain + windowed memory" pattern for CAC/UFC trace roots, but your hypothesis wants Merkle-sharded roots and multiple chains (train/eval/onto/mem). Today's implementation is single-chain plus some additional per-tick artifacts.

## 5) Promotion & Activation (v18): What Gets Verified And What Gets Applied

Promotion and activation are distinct. Promotion builds/verifies a bundle; activation applies it to meta-core's active pointer (or simulates).

### 5.1 Promotion (RE2 + meta-core verify)

- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py:run_promotion()`
  - Reads subverifier receipt; rejects if `status != VALID`.
  - Finds campaign promotion bundle for the dispatch (or returns `SKIPPED:NO_PROMOTION_BUNDLE`).
  - Enforces allowlists (fail closed):
    - For traditional bundles: checks `is_path_allowed`/`is_path_forbidden`.
    - For CCAP bundles: additionally rejects `.omega_cache` touches.
  - Runs meta-core bundle verification (`meta-core/kernel/verify_promotion_bundle.py`).
  - On pass, emits:
    - `omega_activation_binding_v1.json` (tick-local binding for activation)
    - `meta_core_activation_bundle_v1/` directory
    - `omega_promotion_receipt_v1.json` containing `promotion_bundle_hash`, reason/status, and `active_manifest_hash_after` on success.

### 5.2 CCAP Promotion Bundle Variant (Universal Patch/Operator Pipeline)

CCAP promotion bundles have schema `omega_promotion_bundle_ccap_v1` and are validated differently:

- Requires a CCAP verifier receipt:
  - `ccap_receipt_v1.json` (written by `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`)
  - Must have:
    - `decision == "PROMOTE"`
    - `determinism_check == "PASS"`
    - `eval_status == "PASS"`
  - Must match a "realized" receipt inside the subrun:
    - `realized_capsule_receipt_v1.json` under `subrun_root/ccap/realized/`
- Requires that applying the patch/action produces the same tree claimed by the receipt:
  - enforced by `omega_promoter_v1._verify_ccap_apply_matches_receipt()` (RE2 recomputation)

### 5.3 Activation (meta-core apply/rollback)

Activation is called via an adapter:

- `orchestrator/omega_v18_0/applier_v1.py` -> `CDEL-v2/cdel/v18_0/omega_activator_v1.py:run_activation()`

The verifier checks:

- activation success implies `before_active_manifest_hash != after_active_manifest_hash`
- an `omega_activation_binding_v1.json` exists either in meta-core store bundle path or tick-local activation bundle and binds to the tick's binding ID.

## 6) CCAP (Certified Capsule Proposal): Exact Contracts In This Repo

Your EUDRS-U hypothesis introduces CAC/UFC and new gating artifacts. CCAP is the repo's current "universal" proposal/verification pipeline; it matters because it:

- already has authority pins and allowlists,
- already has staged evaluation kernels and operator pools,
- already is promotion-gated and replay-checked.

### 6.1 CCAP Verifier Entry Point (RE2)

- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`
  - Locates a CCAP file in a subrun root (or via explicit relpath).
  - Validates CCAP schema (`ccap_v1`) and canonical filename (`sha256_<ccap_id_hex>.ccap_v1.json`).
  - Loads authority pins and checks pinned allowlists:
    - `authority/authority_pins_v1.json`
    - `authority/ccap_patch_allowlists_v1.json`
  - Enforces "no forbidden touched paths" by parsing unified diff headers (`+++ b/<path>`).
  - Supports payload kinds (observed in code):
    - `PATCH` (unified diff)
    - `GIR` blobs (must exist, scope-checked)
    - `ACTIONSEQ` (operator pool constrained)
  - Runs EK evaluation:
    - `CDEL-v2/cdel/v18_0/ek/ek_runner_v1.py:run_ek()`
  - Emits:
    - `ccap_receipt_v1.json` (and hashed variants)
    - `ccap_refutation_cert_v1.json` on fail-closed refutation
    - "realized" receipts under `subrun_root/ccap/realized/`

### 6.2 Authority Pins (What Is Pinned Today)

Authority pins file (single JSON, canonical):

- `authority/authority_pins_v1.json`
  - `active_ek_id`: `sha256:b4f04c...`
  - `active_op_pool_ids`: `[sha256:c4ed58...]`
  - `active_dsbx_profile_ids`: `[sha256:a77ce5...]`
  - `ccap_patch_allowlists_id`: `sha256:0ce072...`
  - plus canon version ids and RE1/RE2 state pins.

### 6.3 CCAP Patch Allowlist Reality (High Impact For EUDRS-U)

- `authority/ccap_patch_allowlists_v1.json`
  - **Allow prefixes:** `orchestrator/`, `tools/genesis_engine/`, `tools/omega/`, `polymath/registry/`, `campaigns/`
  - **Forbid prefixes:** `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`, `.git/`, `runs/`, `.omega_cache/`

**Implication for EUDRS-U:** you cannot implement core RE2 verifier changes (`CDEL-v2/`) or schema changes (`Genesis/`) through CCAP PATCH proposals under current authority. Any EUDRS-U changes in those areas must use the traditional (non-CCAP) promotion path and will be subject to v19 "axis bundle required" rules (see below).

### 6.4 Sandbox Profile (DSBX)

- `authority/dsbx_profiles/dsbx_profile_core_v1.json`
  - `net: "forbidden"`
  - read-only filesystem except workspace
  - process/file descriptor limits

## 7) Omega v19.0: Axis/Ladder Evidence + Continuity Gates (Already Implemented)

EUDRS-U references "Ladder-Adjoint hierarchical credit" and "fail-closed invariants". This repo's v19 line is the closest existing "progress-as-artifact" mechanism.

### 7.1 v19 Coordinator: Subrun CWD Is Canonical (Critical Wiring Fact)

- `orchestrator/omega_v19_0/coordinator_v1.py`
  - Defines `_chdir(path)` context manager.
  - Before calling `run_subverifier` and `run_promotion`, it executes them **with CWD set to `subrun_root_abs`**:
    - `with _chdir(subrun_root_abs): run_subverifier(...); run_promotion(...)`

This exists because v19 artifacts (notably axis bundles and gate receipts) frequently resolve relative paths from CWD. Your spec must respect this invariant if you add new "relative artifact references".

### 7.2 v19 Promoter: Axis Bundle Is Required For Governed Prefixes

- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`
  - Defines `_GOVERNED_PREFIXES = ("CDEL-v2/cdel/", "Genesis/schema/", "meta-core/", "orchestrator/")`
  - `_requires_axis_bundle(bundle_obj)` returns true if `touched_paths` intersects governed prefixes.
  - Axis bundle loading supports:
    - explicit `axis_upgrade_bundle_ref` artifact ref, or
    - sidecar file `axis_upgrade_bundle_v1.json` next to the promotion bundle.
  - Materializes axis bundle and its referenced artifacts into the meta-core promotion bundle at:
    - `meta_core_promotion_bundle_v1/omega/axis_upgrade_bundle_v1.json`
    - `meta_core_promotion_bundle_v1/omega/continuity/materialized/...`

**Implication for EUDRS-U:** any promotion that touches `CDEL-v2/cdel/` or `Genesis/schema/` will be required (by v19 logic) to include a valid axis bundle, and will be subjected to continuity/treaty/world gates in v19.

### 7.3 Level Attainment Report (Post-Run Evidence Scanner)

- `tools/v19_runs/level_attainment_report_v1.py`
  - Scans `runs_root` for:
    - `sha256_*.omega_promotion_receipt_v1.json`
    - `axis_gate_failure_v1.json`
    - `meta_core_promotion_bundle_v1/omega/axis_upgrade_bundle_v1.json`
  - For promoted receipts with axis bundles, it reads morphism artifacts referenced from the axis bundle and collects `morphism_type`.
  - Computes max level under a monotone coverage rule with a fixed mapping:
    - `LEVELS = (("L0","M_SIGMA"), ("L1","M_SIGMA"), ("L2","M_PI"), ... ("L11","M_T"))`

This is "audit-friendly telemetry" rather than an in-loop authority channel, matching your hypothesis's principle "level attainment is derived, not authority".

## 8) LLM Bridge (Optional, Deterministic Harvest/Replays)

EUDRS-U mentions "untrusted tool-use / router" patterns. This repo contains a deterministic LLM backends contract plus an omega-dispatchable wrapper campaign.

### 8.1 Backend Contract

- `docs/llm_backends.md`
  - `ORCH_LLM_BACKEND`: `mock`, `replay`, `openai_harvest|openai_replay`, `anthropic_*`, `mlx`
  - `ORCH_LLM_REPLAY_PATH`: required for harvest and replay modes
  - `ORCH_LLM_LIVE_OK=1`: required for harvest backends (fail-closed guardrail)

### 8.2 Omega-Dispatchable LLM Wrapper

- `orchestrator/rsi_agi_orchestrator_llm_v1.py`
  - Uses `orchestrator.llm_backend.get_backend()` and calls `backend.generate(prompt)`.
  - Writes evidence artifact `daemon/rsi_agi_orchestrator_llm_v1/state/agi_orchestrator_llm_evidence_v1.json`
  - Writes a promotion bundle that touches:
    - `Extension-1/agi-orchestrator/orchestrator/llm_backend.py`
  - Explicitly avoids v19 governed prefixes to avoid requiring an axis bundle for this campaign.

## 9) What Is NOT Present (Important For Spec Scoping)

Your hypothesis references named bases "QXWMR v1", "CTC v2", "DEP++", "URC-VM". In this checkout, **those strings do not appear anywhere** in tracked code/docs (search excludes `runs/`, `.omega_v18_exec_workspace/`, vendor dirs).

What *is* present and relevant:

- A "capsule" concept inside `Genesis/` (conformance tests, examples, canonicalization), but it is not labeled "CTC v2" in repo naming.
- A universal proposal protocol (CCAP) with pinned authority and evaluation kernels.
- v19 axis/continuity gates which already express "structured progress artifacts" and fail-closed gating.

**Spec consequence:** define EUDRS-U terms as *new* artifacts/contracts, and explicitly map them to existing repo primitives rather than assuming those names already exist.

## 10) Mapping EUDRS-U Constructs To This Repo's Existing Primitives (Recommended)

This section is a pragmatic translation layer so your spec can be implemented in this repository.

### 10.1 Your Root Tuple `R_k` vs Existing Roots

Your hypothesis defines:

`R_k := (SRoot_k, ORoot_k, KRoot_k, CRoot_k, MRoot_k, IRoot_k, WRoot_k)`

Recommended mapping in this repo:

- `SRoot_k` (schemas + canonical pack rules):
  - existing: GCJ-1 canonicalization (`CDEL-v2/cdel/v1_7r/canon.py`) + JSON Schemas (`Genesis/schema/v18_0/*.jsonschema`)
  - new: add EUDRS-U schemas under `Genesis/schema/v18_0/` (or new versioned directory) and pin via normal promotion.
- `ORoot_k` (ontology root):
  - partial analogs exist: polymath registries under `polymath/registry/` are canonical artifacts.
  - but there is no global Merkle ontology root today; EUDRS-U would add a new root artifact type and load/replay logic in RE2.
- `KRoot_k` (strategy root):
  - not a first-class root today; "policy/registry/objectives" are hashed artifacts in omega.
  - EUDRS-U should define a strategy registry artifact and integrate it into decision + replay.
- `CRoot_k` (capsule root):
  - genesis has capsules and receipts, but omega doesn't treat them as a global capsule root.
  - CCAP is closest to "capsule proposals"; EUDRS-U would likely add "capsule families" as artifacts plus verifier rules.
- `MRoot_k` (memory root):
  - existing: episodic memory (`omega_episodic_memory_v1`) and per-run ledgers/receipts.
  - EUDRS-U wants Merkle segments and multi-level indices; these would be new artifact types.
- `IRoot_k` (index roots):
  - existing: observer indexing helpers exist (`omega_observer_index_v1`) but not ML-Index as described.
  - new: introduce ML-Index artifacts and gate them similarly to existing "observer sources".
- `WRoot_k` (weights root):
  - no world-model weight root exists in current omega.
  - EUDRS-U would add Merkle-sharded Q32 tensor blocks and deterministic optimizer logic in RE2.

### 10.2 How To Make EUDRS-U Promotion-Gated In This Repo

Given current constraints:

- CCAP cannot patch `CDEL-v2/` or `Genesis/` (forbidden prefixes).
- v19 requires axis bundles for promotions touching governed prefixes.

So a realistic integration path is:

1. Implement EUDRS-U artifacts + verifier logic in `CDEL-v2/cdel/v18_0/` (new modules) and schemas in `Genesis/schema/v18_0/`.
2. Implement a traditional omega campaign whose promotion bundle touches those files (allowlisted by omega allowlists, not CCAP allowlists).
3. For v19 runs, ensure the promoter emits/sidecars `axis_upgrade_bundle_v1.json` plus referenced morphism artifacts for any governed-prefix change.
4. Have RE2 verifier enforce your CAC/UFC/ontology-stability/ladder-adjoint invariants as part of subverification and/or promotion gating.

## 11) Spec Checklist (What Engineering Needs From You)

To be "seamless" with this repo, your spec should define:

1. **Exact artifact schemas** (JSON schema names, required fields, types).
   - Must be GCJ-1 canonical JSON, no floats.
2. **Deterministic replay surface**:
   - list of files and roots whose hashes are bound into replay.
   - explicit tie-break and ordering rules (TopKDet / ArgMaxDet with `(score desc, id asc)`).
3. **Fail-closed error taxonomy**:
   - reason codes that can be surfaced in receipts and enforced by verifiers.
4. **Promotion bundle integration points**:
   - where CAC/UFC roots live (in promotion bundle directory layout).
   - how axis bundles reference morphism artifacts (`artifact_id` + `artifact_relpath`).
5. **Gates**:
   - CAC thresholds + robustness variants
   - ontology stability gates (STAB-G0..G5)
   - retrieval/memory gates (MEM-G1/MEM-G2)
   - ladder-adjoint invariants (LA-SUM) and where they are checked
6. **Compatibility constraints**:
   - if EUDRS-U touches governed prefixes, it must provide axis bundles and satisfy v19 continuity gates.
   - if any component needs network/tooling, it must respect dsbx profiles and env gates.

## 12) "Where To Look" Appendix (Key Files By Topic)

### Determinism / Canon / Q32

- `CDEL-v2/cdel/v1_7r/canon.py`
- `CDEL-v2/cdel/v18_0/omega_common_v1.py`
- `orchestrator/common/run_invoker_v1.py`

### Omega v18 Tick / Verification

- `orchestrator/omega_v18_0/coordinator_v1.py`
- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
- `CDEL-v2/cdel/v18_0/omega_decider_v1.py`
- `CDEL-v2/cdel/v18_0/omega_temperature_v1.py`
- `CDEL-v2/cdel/v18_0/omega_trace_hash_chain_v1.py`
- `CDEL-v2/cdel/v18_0/omega_episodic_memory_v1.py`
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`

### CCAP / Authority

- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`
- `authority/authority_pins_v1.json`
- `authority/ccap_patch_allowlists_v1.json`
- `authority/operator_pools/operator_pool_core_v1.json`
- `authority/dsbx_profiles/dsbx_profile_core_v1.json`
- `authority/README.md`

### Omega v19 Axis/Ladder

- `orchestrator/omega_v19_0/coordinator_v1.py`
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`
- `tools/v19_runs/run_omega_v19_full_loop.py`
- `tools/v19_runs/level_attainment_report_v1.py`
- `tools/v19_smoke/run_tick_gate_matrix_e2e.py`

### LLM Backend

- `docs/llm_backends.md`
- `agi-orchestrator/orchestrator/llm_backend.py`
- `orchestrator/rsi_agi_orchestrator_llm_v1.py`
