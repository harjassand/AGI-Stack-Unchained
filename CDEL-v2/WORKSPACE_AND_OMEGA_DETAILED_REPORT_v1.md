# Workspace + Omega v18.0 Detailed Technical Report

Date: 2026-02-11  
Repository root: `/Users/harjas/AGI-Stack-Clean`  
Audience: engineering/research handoff

## 1. Report Scope

This report documents:
- The current workspace architecture and how the stack operates end-to-end.
- A deep implementation-grounded analysis of Omega v18.0 behavior and capabilities.
- Current capability surface in both `campaigns/rsi_omega_daemon_v18_0/` and `campaigns/rsi_omega_daemon_v18_0_prod/` profiles.

Primary code anchors inspected:
- Orchestration: `orchestrator/rsi_omega_daemon_v18_0.py`, `orchestrator/omega_v18_0/coordinator_v1.py`
- Omega runtime: `CDEL-v2/cdel/v18_0/*.py`
- Replay verifier: `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
- Contracts: `Genesis/schema/v18_0/*.jsonschema`
- Config packs: `campaigns/rsi_omega_daemon_v18_0/*`, `campaigns/rsi_omega_daemon_v18_0_prod/*`
- Trust roots: `meta-core/`, `authority/`

---

## 2. Workspace Architecture (Current State)

## 2.1 Top-Level Composition

The workspace is a multi-layer deterministic RSI stack.

Core directories:
- `meta-core/`: RE1 trusted constitutional kernel / activation system.
- `CDEL-v2/`: RE2 deterministic execution + verification engine (Omega lives here).
- `orchestrator/`: daemon and campaign orchestration entrypoints/adapters.
- `Genesis/`: schema and protocol contracts.
- `authority/`: authority pins, patch allowlists, evaluation kernel references.
- `campaigns/`: campaign packs and policy/config materialization sources.
- `polymath/`: domain registry/portfolio/scout state.
- `runs/`: content-addressed run artifacts.

Observed scale snapshot:
- Workspace tracked files: ~10,396 (`rg --files`).
- `CDEL-v2/cdel/v18_0/`: 489 files, 55 top-level Python modules.
- Omega tests: 119 daemon tests in `CDEL-v2/cdel/v18_0/tests_omega_daemon/`, 122 v18 tests total across test dirs.

## 2.2 Trust and Control Planes

Operational trust split:
- Trusted root / constitutional anchor: `meta-core/`.
- Deterministic runtime + verifiers: `CDEL-v2/cdel/v18_0/`.
- Proposal execution surfaces: campaign modules, CCAP payloads, skill adapters.
- Governance anchors: `authority/authority_pins_v1.json`, `authority/ccap_patch_allowlists_v1.json`.

Important design property:
- Untrusted or semi-trusted proposal outputs do not directly mutate trust roots.
- Promotion and activation are gated by subverification, promotion checks, meta-core verification, and health/rollback logic.

## 2.3 How The Workspace Executes Work

Execution is run-centric and artifact-addressed:
1. Daemon loads a pack (`rsi_omega_daemon_pack_v1.json`) and freezes config into run-local config.
2. It emits canonical-hashed artifacts by stage into state folders.
3. Every stage writes receipts and hashes that are replay-verifiable.
4. Verifiers re-open artifacts by hash and recompute expected outputs.
5. Any mismatch fails closed (`INVALID:*`) and blocks acceptance.

Canonical output structure (Omega run):
- `runs/<run_id>/daemon/rsi_omega_daemon_v18_0/state/{state,observations,issues,decisions,dispatch,ledger,snapshot,subruns,...}`

## 2.4 Governance and Authority Surfaces

Authority pin file currently carries active IDs for:
- Evaluation kernel (`active_ek_id`)
- Operator pools (`active_op_pool_ids`)
- DSBX profiles (`active_dsbx_profile_ids`)
- Canon IDs and RE1/RE2 state IDs

CCAP patch policy (`authority/ccap_patch_allowlists_v1.json`):
- Allow prefixes include: `orchestrator/`, `tools/omega/`, `polymath/registry/`, `campaigns/`.
- Forbid prefixes include: `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`, `.git/`, `runs/`, `.omega_cache/`.

This prevents CCAP lanes from patching critical trust roots directly.

---

## 3. Omega v18.0 System Deep Dive

## 3.1 Entrypoint and Tick Driver

Entrypoint:
- `orchestrator/rsi_omega_daemon_v18_0.py`
- Modes: `once` and `loop`
- Core call: `run_tick(...)` in `orchestrator/omega_v18_0/coordinator_v1.py`

Coordinator responsibilities:
- Create stage directories.
- Acquire run lock (`LOCK`) to serialize tick writes.
- Freeze pack config.
- Load policy/registry/objectives/runaway/budgets/allowlists/healthcheck/goal queue.
- Run Observe -> Diagnose -> Decide -> Dispatch -> Subverify -> Promote -> Activate.
- Emit state/ledger/trace/snapshot/perf artifacts.
- Trigger `SAFE_HALT` under hard failures.

## 3.2 Tick Lifecycle (Implemented)

### Stage A: Config Freeze + State Bootstrap

- `freeze_pack_config(...)` copies required config artifacts into run config dir.
- If no prior state, `default_state_from_hashes(...)` creates baseline state with default budget remaining.
- Active manifest hash is read from meta-core (`meta-core/active/ACTIVE_BUNDLE`) and bound into state.

### Stage B: Observe

`CDEL-v2/cdel/v18_0/omega_observer_v1.py` builds `omega_observation_report_v1` by loading deterministic source artifacts.

Metric families currently integrated:
- Core runtime:
  - `metasearch_cost_ratio_q32`
  - `hotloop_top_share_q32`
  - `build_link_fraction_q32`
  - `science_rmse_q32`
  - `verifier_overhead_q32`
  - `brain_temperature_q32`
- Stability/performance carry-forward:
  - promotion reject/invalid rates
  - runaway blocked rates
  - prior tick total ns
- Polymath:
  - coverage, void score, blocked/ready counts
  - scout staleness
  - portfolio score/domain count/cache-hit mean
- GE SH1 lane:
  - `ge_promote_rate_rat`, `ge_mean_stps_delta_q32`
- Legacy skill metrics:
  - transfer/ontology/flywheel/thermo/persistence/alignment/math/science/swarm/model-genesis signals

Observer behavior highlights:
- Uses observer index fast-path (`omega_observer_index_v1`).
- Falls back deterministically on missing state inputs for core required sources.
- Carries metric series with bounded window (64).

### Stage C: Diagnose

`omega_diagnoser_v1.py` converts metric thresholds into issue bundle entries.

Issue classes currently encoded:
- `SEARCH_SLOW`, `SEARCH_STALL`
- `HOTLOOP_BOTTLENECK`
- `BUILD_BOTTLENECK`
- `SCIENCE_ACCURACY_STALL`
- `PROMOTION_REJECT_RATE`
- `VERIFIER_OVERHEAD`
- `DOMAIN_VOID_DETECTED`
- `POLYMATH_SCOUT_STALE`
- `POLYMATH_PORTFOLIO_REGRESSION`
- `DOMAIN_READY_FOR_CONQUER`
- `DOMAIN_BLOCKED_LICENSE`, `DOMAIN_BLOCKED_SIZE`, `DOMAIN_BLOCKED_POLICY`

### Stage D: Goal Synthesis

`orchestrator/omega_v18_0/goal_synthesizer_v1.py` rewrites effective queue with deterministic heuristics:
- Ensures floor pending levels by capability.
- Injects issue-driven goals.
- Handles boredom/family coverage injection.
- Adds runaway-recovery goals when blocked/noop patterns appear.
- Uses episodic memory to suppress churn (e.g., repeated `ALREADY_ACTIVE`, repeated no-promotion-bundle tails, repeated invalids).
- Supports Polymath scout/bootstrap/conquer goal injections.

### Stage E: Decide

`omega_decider_v1.py` produces `omega_decision_plan_v1` with recompute proof.

Action kinds:
- `RUN_CAMPAIGN`
- `RUN_GOAL_TASK`
- `NOOP`
- `SAFE_HALT`

Decision properties:
- Hash-match checks for policy/registry; mismatch => `SAFE_HALT`.
- Goal-first selection with temperature-based class ranking.
- Rule-based fallback from policy IR.
- Optional runaway mode route/escalation/intensity selection.
- Deterministic tie-break trace (`tie_break_path`).

### Stage F: Dispatch

`omega_executor_v1.py`:
- Resolves campaign from registry (campaign or capability route).
- Materializes isolated subrun execution workspace.
- Runs orchestrator module with pinned `PYTHONPATH` and controlled env.
- Guards forbidden skip-verifier env knobs in production mode.
- Emits `omega_dispatch_receipt_v1` and dispatch context.
- Computes subrun tree hash.

### Stage G: Subverification

`omega_promoter_v1.py::run_subverifier(...)`:
- Invokes per-campaign verifier module with `--mode full`.
- Handles verifier argument variants (e.g., v12 code verifier, CCAP verifier).
- Supports replay repo snapshot path for v14 verifier lane.
- Emits `omega_subverifier_receipt_v1` with `VALID/INVALID` and normalized reason codes:
  - `SCHEMA_FAIL`, `MISSING_STATE_INPUT`, `NONDETERMINISTIC`, `MODE_UNSUPPORTED`, `VERIFY_ERROR`, `UNKNOWN`

### Stage H: Promotion

`omega_promoter_v1.py::run_promotion(...)` gates promotion.

Required checks include:
- Subverifier must be `VALID`.
- Promotion bundle must exist unless legitimately skipped.
- Test-plan receipt required for campaigns configured to require it.
- EK meta-verify receipt required for authority/evaluation-kernel touching bundles.
- Non-CCAP: touched paths must pass allowlist+forbidden checks.
- CCAP: stricter path consistency checks + receipt consistency + apply consistency replay.
- Meta-core promotion verify (`meta_core_promo_verify_receipt_v1`) must pass.

Promotion statuses:
- `PROMOTED`, `REJECTED`, `SKIPPED`

Promotion reason-code surface includes:
- `NO_PROMOTION_BUNDLE`, `SUBVERIFIER_INVALID`, `META_CORE_REJECT`, `FORBIDDEN_PATH`
- `TEST_PLAN_RECEIPT_MISSING_OR_FAIL`, `ALREADY_ACTIVE`, `TOOLCHAIN_MISMATCH`, `UNKNOWN`
- `CCAP_RECEIPT_MISSING_OR_MISMATCH`, `CCAP_RECEIPT_REJECTED`, `CCAP_APPLY_MISMATCH`, `CCAP_TOUCHED_PATHS_INVALID`
- `EK_META_VERIFY_MISSING_OR_FAIL`

### Stage I: Activation + Rollback

`omega_activator_v1.py::run_activation(...)`:
- Requires `PROMOTED` promotion receipt.
- Applies meta-core activation bundle (live mode) or simulated pointer hash path when configured.
- Verifies binding integrity (`omega_activation_binding_v1`) against resulting active bundle.
- Runs healthcheck suite.
- Emits `omega_activation_receipt_v1` and optional `omega_rollback_receipt_v1` on health failure.

Activation reason enums:
- `HEALTHCHECK_PASS`, `HEALTHCHECK_FAIL`, `POINTER_SWAP_FAILED`, `META_CORE_DENIED`, `BINDING_MISSING_OR_MISMATCH`, `ROLLBACK_REQUIRED`

### Stage J: State, Ledger, Trace, Snapshot, Perf

Coordinator emits:
- `omega_state_v1`
- append-only ledger events (`omega_ledger_v1.jsonl`)
- `omega_trace_hash_chain_v1` (H0 + chained artifact hashes)
- `omega_tick_snapshot_v1` as canonical per-tick pointer set
- perf/outcome/stats/scorecard/hotspots/episodic memory artifacts

SAFE_HALT behavior:
- Triggered on hard safety conditions (e.g., invalid subverifier, forbidden-path cases).
- Persisted in tick outcome and ledger event sequence.

## 3.3 Replay Verifier (Fail-Closed)

`verify_rsi_omega_daemon_v1.py` recomputes major stages and enforces consistency.

Key verifier guarantees:
- Snapshot and hash binding checks for all referenced artifacts.
- Observer source artifact reloading and metric recomputation.
- Diagnoser and decider recomputation equality checks.
- Runaway-state transition recomputation checks (when enabled).
- Subverifier replay enforcement for promoted flows.
- Promotion/activation consistency checks with binding presence and pointer-change semantics.
- Forbidden-path re-evaluation against allowlists.
- Trace hash-chain recomputation exactness.
- Absolute-path sanitization checks on payloads.

Output contract:
- `VALID` or fail-closed `INVALID:<reason>`.

---

## 4. Omega Capability Inventory (Current)

## 4.1 Dev Profile (`campaigns/rsi_omega_daemon_v18_0/`)

Registry summary:
- Total capabilities: 19
- Enabled now: 3

Enabled campaigns:
- `rsi_sas_code_v12_0`
- `rsi_sas_metasearch_v16_1`
- `rsi_sas_val_v17_0`

Disabled but present:
- Core self-opt, polymath scout/bootstrap/conquer, GE SH1 optimizer, skill adapters, model-genesis lane.

Policy rules in active dev policy: 9
- Search-slow routes to v12/v16/v17 fallback.
- Build/hotloop routes to v17.
- Polymath stale/void/ready routes exist.

Objectives (4 metrics):
- `metasearch_cost_ratio_q32` (MINIMIZE)
- `hotloop_top_share_q32` (MINIMIZE)
- `build_link_fraction_q32` (MINIMIZE)
- `science_rmse_q32` (MINIMIZE)

Runaway config:
- Present but `enabled: false` in dev profile.

Goal queue baseline:
- 3 base pending goals (code/metasearch/val).

## 4.2 Prod Profile (`campaigns/rsi_omega_daemon_v18_0_prod/`)

Registry summary:
- Total capabilities: 22
- Enabled now: 6

Enabled campaigns:
- `rsi_sas_code_v12_0`
- `rsi_sas_kernel_v15_0`
- `rsi_sas_metasearch_v16_1`
- `rsi_sas_science_v13_0`
- `rsi_sas_system_v14_0`
- `rsi_sas_val_v17_0`

Runaway config:
- `enabled: true`
- Escalation + per-metric route tables + per-campaign intensity env overrides configured.

Goal queue:
- 300 pending goals (50 per enabled core capability family above).

## 4.3 Budget and Patch Governance Surface

Dev budget pack (`omega_budgets_v1.json`) includes:
- Daily Q32 ceilings for cpu/build/verifier
- Disk budget
- tick/day and total tick limits
- rollback and per-tick wallclock caps

Allowlist policy (`omega_allowlists_v1.json`) includes:
- Allowed patch prefixes across orchestrator/cdel/tool/schema/domain/polymath surfaces.
- Forbidden prefixes include meta-core engine/kernel and verifier path families.

---

## 5. Data Contracts and Artifact Model

Important schema families in `Genesis/schema/v18_0/`:
- Omega state/control: state, decision, policy, objectives, registry, budgets, allowlists
- Omega receipts: dispatch, subverifier, promotion, activation, rollback
- Tick artifacts: observation, issue bundle, stats, scorecard, perf, snapshot, trace chain, episodic memory, hotspots
- CCAP: `ccap_v1`, `ccap_receipt_v1`, `ccap_refutation_cert_v1`
- Meta-core bridge: `meta_core_promo_verify_receipt_v1`, `omega_activation_binding_v1`
- Polymath: domain registry/pack/corpus/portfolio/void/scout/equivalence/fetch

Observed schema breadth in `v18_0` folder:
- 56 schema files total
- 45 directly relevant to omega/ccap/polymath/meta-core-promo/healthcheck pack lane

---

## 6. Current Runtime Footprint Snapshot

Run directory counts (workspace snapshot):
- `runs/rsi_omega_daemon_v18_0_tick_*`: 20
- `runs/rsi_omega_daemon_v18_0_prod_tick_*`: 45
- `runs/rsi_omega_runaway_v18_1*`: 209
- `runs/rsi_omega_benchmark_v18_0*`: 1

Observed polymath current registry state:
- `polymath_domain_registry_v1`: 1 active domain (`pubchem_weight300`)
- `polymath_portfolio_v1`: score `q=0`, 0 domains in portfolio

Sample recent omega benchmark-style run (`runs/phase_u1_g1_20260211_092548`):
- Observation shows high metasearch ratio and hotloop concentration with low build fraction.
- Issues include `SEARCH_SLOW`, `SEARCH_STALL`, and `DOMAIN_READY_FOR_CONQUER` on recent ticks.
- Recent tick outcomes include valid subverification with `SKIPPED: ALREADY_ACTIVE` promotion outcomes.

---

## 7. Test Surface and Verification Confidence

Omega v18 test posture is strong and oriented around failure modes and replay:
- 119 daemon tests in `tests_omega_daemon`.
- Coverage themes include:
  - determinism/recompute correctness
  - fail-closed behavior on missing/mismatch artifacts
  - forbidden path and allowlist enforcement
  - activation binding checks and meta-core gate requirements
  - subverifier replay requirements on promoted paths
  - runaway/goal synthesis behaviors
  - CCAP legality/schema/enforcement checks
  - observer fast-path + fallback source behavior

This is a meaningful assurance base for deterministic governance behavior.

---

## 8. Practical Interpretation of Current Omega Capability

What Omega v18.0 currently does well:
- Deterministic tick orchestration with canonical content-addressed artifacts.
- Strong fail-closed verification and replay constraints.
- Multi-stage acceptance path (dispatch -> subverify -> promote -> activate) with no silent bypass.
- Integration with meta-core promotion verification and activation binding checks.
- Built-in adaptive control concepts (temperature bands, runaway policy, episodic suppression, goal synthesis).
- Cross-domain metric scaffolding (polymath + skill/GE signals) in observation plane.

Current practical limits (implementation-visible):
- Many advanced capabilities are present in registry but disabled in the dev profile.
- Deep continuity theorem artifacts are not first-class universal acceptance objects in v18.
- World snapshot/treaty/federation semantics are not native universal gates in current omega contracts.
- Live polymath portfolio compounding remains sparse (registry active, portfolio currently empty/zero-scored).

---

## 9. File-Level Index (Quick Reference)

Core Omega runtime:
- `orchestrator/rsi_omega_daemon_v18_0.py`
- `orchestrator/omega_v18_0/coordinator_v1.py`
- `CDEL-v2/cdel/v18_0/omega_observer_v1.py`
- `CDEL-v2/cdel/v18_0/omega_diagnoser_v1.py`
- `CDEL-v2/cdel/v18_0/omega_decider_v1.py`
- `CDEL-v2/cdel/v18_0/omega_executor_v1.py`
- `CDEL-v2/cdel/v18_0/omega_promoter_v1.py`
- `CDEL-v2/cdel/v18_0/omega_activator_v1.py`
- `CDEL-v2/cdel/v18_0/omega_runaway_v1.py`
- `CDEL-v2/cdel/v18_0/omega_state_v1.py`

Replay and contract enforcement:
- `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py`
- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py`
- `meta-core/kernel/verify_promotion_bundle.py`

Config and policy packs:
- `campaigns/rsi_omega_daemon_v18_0/*`
- `campaigns/rsi_omega_daemon_v18_0_prod/*`

Trust anchors:
- `authority/authority_pins_v1.json`
- `authority/ccap_patch_allowlists_v1.json`
- `meta-core/active/ACTIVE_BUNDLE`

---

## 10. Bottom Line

Omega v18.0 in this workspace is a deterministic, fail-closed governance engine with a robust replay verifier and meta-core-gated promotion/activation bridge. Its strongest capabilities are in reproducibility, policy gating, and safety-conservative acceptance. Its forward capability envelope (self-opt/core skills/polymath/runaway escalation) is structurally present, with more of it enabled in the prod profile than dev.
