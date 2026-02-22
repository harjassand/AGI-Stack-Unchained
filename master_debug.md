# FRONTIER_HEAVY Target / Curriculum Schema

## Quick answer

There is **no dedicated `FRONTIER_HEAVY` target model** (JSON schema, dataclass, or DB table schema) in this branch.

`FRONTIER_HEAVY` is:

- a **declared class label** for a capability in `utility_policy_v1`, and
- a **runtime routing bucket** enforced by `microkernel_v1` (frontier lane / dependency debt / routing receipts).

The “objective / constraints / success criteria” are not fields on a target schema tied to `FRONTIER_HEAVY`; they are split across:

- campaign behavior (external target assets referenced by `target_relpath`),
- capability policy (`heavy_policies`),
- and debt/attempt telemetry (`dependency_debt_state`, `dependency_routing_receipt`, `utility_proof_receipt`).

---

## What *does* define frontier behavior

### 1) `utility_policy_v1`: declared classes + heavy policy

The frontier class gate is in utility policy, not in a target schema.

- Declared classes include:
  - `FRONTIER_HEAVY`
  - `CANARY_HEAVY`
  - `BASELINE_CORE`
  - `MAINTENANCE`
- `FRONTIER_HEAVY` is treated as a “heavy” class.
- A capability is tagged as `FRONTIER_HEAVY` through the `declared_class_by_capability` mapping.

`heavy_policies` is where frontier-specific behavior is expressed:

- `probe_suite_id`
- `stress_probe_suite_id`
- `primary_signal`
- `primary_threshold_u64`
- `stress_signal`
- `stress_threshold_u64`
- optional `policy_artifact_relpath`

These are the fields the runtime compares against to decide frontier-heavy success/failure characteristics.

### 2) Mission goal / campaign object: where frontier goals are introduced

There is no `FRONTIER_HEAVY` field in the mission goal schema itself.  
A frontier goal is effectively:

- a goal for a **capability that resolves to `FRONTIER_HEAVY`**, and
- a goal assigned to the frontier lane / debt regime in profile + debt state.

Key implication:
- A goal can become frontier just by selecting the capability+policy class path; there is no separate “frontier target model” that contains those fields itself.

### 3) Goal queue row shape (actual persisted “target-like” object)

Frontier tracking is done on queue rows and debt receipts.  
The queue entry has this canonical shape:

- `goal_id`
- `capability_id`
- `status`
- optional `frontier_id`

For frontier behavior, `frontier_id` is the coupling point used by debt/attempt logic.

### 4) `long_run_profile_v1`: frontier lane + debt policy inputs

The long-run profile contributes the frontier universe:

- `lanes.frontier_capability_ids`
- `dependency_debt.debt_limit_u64`
- `dependency_debt.max_ticks_without_frontier_attempt_u64`
- optional `utility_policy_relpath` / `utility_policy_id` link back to policy context

This means frontier is runtime policy + scheduling context, not a standalone target artifact.

### 5) Debt/routing/proof contracts that enforce frontier constraints

Constraint-like mechanics for frontier are encoded in debt and receipt models:

- `dependency_debt_state_v1`
  - frontier debt accounting
  - ticks, debt counters, hard-lock flags
  - attempt history and blocking metadata
- `dependency_routing_receipt_v1`
  - selected class
  - blocked / forced frontier attempts
  - routing reason codes
- `utility_proof_receipt_v1`
  - frontier/stress validation proof payload details

This is where repeated failures, forced retries, and backoff-like behavior are persisted and interpreted.

---

## Exact runtime flow for `FRONTIER_HEAVY`

1. A mission goal is ingested and normalized.
2. For its `capability_id`, kernel resolves class via policy mapping:
   - `declared_class_by_capability[capability_id]`
3. If class is `FRONTIER_HEAVY` (and in frontier lane policy), frontier debt/attempt routing path is used.
4. `dependency_routing_receipt` records routing reason and whether this was a forced frontier attempt.
5. `dependency_debt_state` is updated with ticks/counters/hard-lock indicators.
6. `utility_proof_receipt` tracks proof/stress checks tied to heavy policy thresholds/signals.
7. If a frontier target relpath is needed, campaign-level target resource is resolved dynamically at ingest time.

Note: frontier constraints are “policy + debt + receipts,” not an inline schema object.

---

## Why your request for objective/constraints/success criteria is currently unmet by design

You will not find a single schema/dataclass with:

- `objective`
- `constraints`
- `success_criteria`

for `FRONTIER_HEAVY`.

Those concerns live in:
- external target assets referenced by the campaign (`target_relpath`),
- heavy policy thresholds/signals (`utility_policy_v1`),
- and execution proof/debt telemetry.

If you need strict machine-enforced objective/constraint schema, it does not exist yet as part of the frontier target contract.

---

## What to synthesize if system writes its own frontier-like targets

Given the current code:

- The **minimum frontier-capable synthesized object** is a normal frontier-capability goal row plus frontier debt context:

```json
{
  "goal_id": "<uuid-or-string-id>",
  "capability_id": "<capability whose class resolves to FRONTIER_HEAVY>",
  "frontier_id": "<frontier bucket or cohort id>"
}
```

- If the campaign requires a target artifact, also provide:

```json
{
  "...": "...",
  "target_relpath": "<pack-relative path to target descriptor>"
}
```

This is outside strong schema validation today; ensure your target descriptor is compatible with the specific campaign logic you call into.

To be frontier-capability correct, you must also guarantee that policy is configured with the heavy fields for that capability.

---

## What would be required for an actual `FRONTIER_MEDIUM` contract

Right now, `FRONTIER_MEDIUM` is **not recognized** and resolves to unclassified/other paths.

To make `FRONTIER_MEDIUM` valid and meaningful, you would need coordinated updates in at least:

1. Add enum/class support in utility policy schema and code:
   - `FRONTIER_MEDIUM` in declared-class enum.
   - Router/normalization fallback behavior that currently normalizes unknown classes.
2. Update heavy class/grouping logic:
   - decide whether it should share heavy debt/routing behavior with `FRONTIER_HEAVY` or have its own branch.
3. Update frontier lane/dependency debt logic:
   - classification branching where class-specific handling is done.
4. Add policy fields/rules for success/stress semantics (or reuse heavy policy schema).
5. Update any downstream code paths that branch on class constants.

Until then, any external generator that emits `FRONTIER_MEDIUM` will not trigger frontier-heavy behavior in this branch.

---

## File map used in this analysis

- `orchestrator/omega_v19_0/microkernel_v1.py`
- `orchestrator/omega_v19_0/mission_goal_ingest_v1.py`
- `orchestrator/omega_v19_0/goal_synthesizer_v1.py`
- `Genesis/schema/v19_0/utility_policy_v1.jsonschema`
- `Genesis/schema/v19_0/long_run_profile_v1.jsonschema`
- `Genesis/schema/v19_0/rsi_omega_daemon_pack_v2.jsonschema`
- `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_routing_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/utility_proof_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/mission_request_v1.jsonschema`
- `Genesis/schema/v19_0/mission_goal_ingest_receipt_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_goal_queue_v1.jsonschema`
- `CDEL-v2/Genesis/schema/v18_0/omega_capability_registry_v2.jsonschema`
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`

# 2. The Evaluation Kernel & Verifier Interface

## 2.1 Pinned evaluation kernel execution (what actually runs)

In v18, the “pinned evaluation kernel” check is in `CDEL-v2/cdel/v18_0/ek/ek_runner_v1.py` (`run_ek`) and is enforced before scoring:

- It reads authority pins from `authority/authority_pins_v1.json`.
- It checks that `ccap.meta.ek_id == active_ek_id` from the pins (`_load_active_ek`, `EK_ID_NOT_ACTIVE` on mismatch).
- It loads an `evaluation_kernel_v1` payload from `authority/evaluation_kernels/` with a digest that matches `active_ek_id`.
- It requires stage sequence exactly `REALIZE`, `SCORE`, `FINAL_AUDIT` (strict order, exact names).

Execution for a CCAP candidate is: 

1. `_resolve_patch_bytes_for_payload(...)` (PATCH/ACTIONSEQ/GIR patch materialization)
2. `_realize_once(...)` once (and second time in strict mode)
3. `_run_score_stage(...)` (base vs candidate scoring)
4. Final audit marker write

Important detail:
- A special survival path (`OMEGA_SURVIVAL_DRILL`) can run only one `REALIZE` pass and skip the second realize + score path.
- Double-run determinism checks are only applied in normal mode.
- If `OMEGA_ENFORCE_DETERMINISTIC_COMPILATION=1`, determinism mismatches force `determinism_check= DIVERGED` + `eval_status=REFUTED` + `decision=REJECT`.

## 2.2 Actual verifier return types (current code)

`run_ek(...)` returns a Python `dict`, not a dedicated `VerifierReceipt` class. The current contract is:

- `determinism_check`: `"PASS" | "DIVERGED" | "REFUTED"`
- `eval_status`: `"PASS" | "FAIL" | "REFUTED"`
- `decision`: `"PROMOTE" | "REJECT"`
- `refutation`: `dict | None`
- `applied_tree_id`: `sha256:...`
- `realized_out_id`: `sha256:...` or `""`
- `cost_vector`: `{cpu_ms, wall_ms, mem_mb, disk_mb, fds, procs, threads}`
- `logs_hash`: `sha256:...`
- Optional score summaries:
  - `scorecard_summary`
  - `score_base_summary`
  - `score_cand_summary`
  - `score_delta_summary`

`verify_ccap_v1.verify(...)` wraps this and returns:

- `(receipt_payload: dict, refutation_code: str | None)`

`receipt_payload` is serialized as `ccap_receipt_v1.json` under verifier output.

Lower in the stack, `OmegaVerifierClient.verify(...)` (`tools/omega/omega_verifier_client_v1.py`) is a lightweight worker wrapper used by runner code. Its typed return is:

- `(ok: bool, verdict_or_reason: str, detail: str)`
- On success: `verdict` typically `"VALID"`
- On failure: `ok=False`, with reason/detail such as `VERIFY_ERROR`

## 2.3 What a completed CCAP verification tick “spits out”

### Primary artifacts written per CCAP verify

- `subrun/<...>/verifier/ccap_receipt_v1.json` (canonicalized receipt)
- optional `ccap_refutation_cert_v1.json` in `subrun/<...>/ccap/refutations/`
- optional `realized_capsule_receipt_v1.json` if promoted
- optional EK-stage artifacts under `subrun/<...>/ccap/ek_runs/...`

### `ccap_receipt_v1` schema fields (relevant)

From `Genesis/schema/v18_0/ccap_receipt_v1.jsonschema` and `verify_ccap_v1._receipt_payload`, the verifier writes:

- required:
  - `schema_version`, `ccap_id`, `base_tree_id`, `applied_tree_id`, `realized_out_id`, `ek_id`, `op_pool_id`, `auth_hash`
  - `determinism_check`, `eval_status`, `decision`
  - `cost_vector`, `logs_hash`
- optional summaries if present:
  - `scorecard_summary`
  - `score_base_summary`
  - `score_cand_summary`
  - `score_delta_summary`

### What is **not** present

- No `tests_passed`
- No `utility_score`
- No `touched_paths` in verifier receipt
- No explicit per-capability holdout split in the receipt payload

`touched_paths` exists in CCAP promotion bundle shape (`omega_promotion_bundle_ccap_v1`), not in the verifier receipt.

## 2.4 Verifier success/fail semantics today

The CCAP verifier computes decision as:

- `PROMOTE` only when:
  - kernel load/auth/eval setup passes
  - determinism check is `PASS`
  - scoring stage passes gate logic (`run_ek` returns `decision=PROMOTE`)
- Otherwise `REJECT` and `eval_status` set to `FAIL` or `REFUTED` with a refutation code.

Common returned refutation codes include:
- `EK_ID_NOT_ACTIVE`, `NO_IMPROVEMENT`, `BUDGET_EXCEEDED`, `EVAL_STAGE_FAIL`, `NONDETERMINISM_DETECTED`, `BASE_TREE_MISMATCH`, `FORBIDDEN_PATH`, etc.

## 2.5 Tick-level “verifier” object in orchestrator flow

At dispatcher/promoter scope, the verifier module result is additionally represented as `omega_subverifier_receipt_v1` (`status`, `reason_code`) and CCAP artifacts may be recomputed/loaded/fallbacked:
- `status`: `VALID | INVALID`
- `result.reason_code`: e.g. `VERIFY_ERROR`

So the observable tick-end verifier surface is usually:

- `omega_subverifier_receipt_v1` for subverifier execution status
- `ccap_receipt_v1` for CCAP decision/eval details (where available)
- `omega_promotion_receipt_v1` after promotion routing

## 2.6 Practical implication for Capability Delta / holdout tests

For Capability Delta bypass logic, current code gives you these stable anchors:

- `decision` + `determinism_check` + `eval_status` for hard gating (promotion readiness)
- `score_*_summary` values (`median_stps_non_noop_q32`, `promotions_u64`, `activation_success_u64`, plus floating `non_noop_ticks_per_min_f64`)
- `score_delta_summary` computed as candidate-base delta already exists (useful for anti-Goodhart checks)

It does **not** currently expose:

- fine-grained test-pass/fail vectors
- heldout-vs-in-domain pass rates directly in verifier receipt

So if Capability Delta needs holdout metrics, the current minimum-invasive route is:
1. extend scoring output contract (scorecard fields / `score_*_summary` or an attached holdout score artifact hash), or
2. consume benchmark run artifacts under EK run dirs (`.../ek_runs/.../score/...`) and derive your holdout metrics from those artifacts downstream.

# 3. The Tick State / Memory Object

This section maps the long-run dependency-control state machine to a concrete persisted object.

## 3.1 Which object tracks cross-tick state

The run-wide memory for this mechanism is `dependency_debt_state_v1`.

It is:

- Read from `long_run/debt` via `_load_prev_dependency_debt_state` in `orchestrator/omega_v19_0/microkernel_v1.py`.
- Rebuilt from defaults by `_default_dependency_debt_state`.
- Updated every long-run tick inside `tick_once`.
- Persisted atomically with `dependency_debt_state_v1.json` via `_write_payload_atomic`.

Schema path: `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`.

Current required fields include:

- `ticks_without_frontier_attempt_by_key`
- `last_frontier_attempt_tick_u64`
- `hard_lock_active_b`
- `hard_lock_debt_key`
- `hard_lock_goal_id`
- `maintenance_since_last_frontier_attempt_u64`
- `frontier_attempts_u64`
- plus debt maps, reason counters, and last-attempt metadata.

## 3.2 How “ticks since frontier progress” is represented

The direct tracker is:

- `ticks_without_frontier_attempt_by_key: dict[str, int]`.

It is keyed by frontier debt key built from frontier goal identity.

- Built in `_pending_frontier_goals` via `_derive_debt_key(frontier_id, capability_id)`.
- Debt key is persisted in each frontier route row as `debt_key`.
- `_forced_frontier_debt_key(...)` consumes this key map and threshold config:
  - force if `debt_by_key >= debt_limit_u64`, or
  - force if `ticks + 1 + anticipate_without_attempt_u64 >= max_ticks_without_frontier_attempt_u64`.

Per-tick update logic in `tick_once`:

- On each long-run tick, the update loop starts from `prev_dependency_debt_state`.
- For each frontier debt key:
  - if the tick counts as a frontier attempt for that key, ticks reset to `0`.
  - otherwise ticks increment by `1`.
- The same loop also projects legacy `debt_by_goal_id` and `ticks_without_frontier_attempt_by_goal_id` for compatibility.
- `last_frontier_attempt_tick_u64`, `last_frontier_attempt_debt_key`, `last_frontier_attempt_goal_id` are overwritten only when a frontier attempt is successfully counted.

There is also a run-level maintenance-style progress guard:

- `maintenance_since_last_frontier_attempt_u64`:
  - set to `0` when frontier attempt is counted,
  - set to `1` and carried forward while frontier goals are pending but no frontier counted,
  - reset to `0` otherwise.

This gives two orthogonal progress signals:
- frontier-key local “stalled duration” in `ticks_without_frontier_attempt_by_key`,
- last-attempt adjacency in `last_frontier_attempt_*` and `maintenance_since_last_frontier_attempt_u64`.

## 3.3 How hard-lock current status is represented

Hard-lock is represented by:

- `hard_lock_active_b`
- `hard_lock_debt_key`
- `hard_lock_goal_id`

Computation is done near the long-run debt update block:

- `_forced_frontier_debt_key(...)` is called first with anticipated no-attempt drift (`anticipate_without_attempt_u64=1`) to decide pre-tick forcing.
- `forced_frontier_attempt_b` is a direct boolean from that call.
- `next_hard_lock_active_b` is persisted as:
  - `forced_frontier_attempt_b` OR there was a forced key from prior state.
- `hard_lock_debt_key` and `hard_lock_goal_id` retain the active forced target while lock is in effect.

Routing then attaches a lock transition reason:

- `hard_lock_became_active_b` detects a false->true transition in lock state.
- If lock is active and the selected action is not a counted frontier attempt, `_with_frontier_dispatch_failed_pre_evidence_reason` adds `FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE`.
- The lock reason is surfaced via dependency routing receipt fields:
  - `frontier_goals_pending_b`,
  - `forced_frontier_attempt_b`,
  - `reason_codes`.

`long_run_tick_index_row_v1` copies `hard_lock_active_b` into the long-run ledger row in `scripts/run_long_disciplined_loop_v1.py` for time-series visibility.

## 3.4 Why this object is “the memory object” across ticks

It persists all run-level frontier debt that would otherwise be lost:

- frontier pressure accumulators (`debt_by_key`, `ticks_without_frontier_attempt_by_key`),
- frontier history projections (`debt_by_goal_id`, `first_debt_tick_by_key`),
- lock continuity (`hard_lock_*` + reason),
- run counters (`frontier_attempts_u64`, `maintenance_count_u64`, capability-level heavy counters).

Because the payload is canonicalized and written each tick, `_forced_frontier_debt_key` in the next tick can continue with exactly the same debt pressure state as the previous tick.

## 3.5 Where to inject `CURRICULUM_DEGRADE_MODE` and scaffold limits

Current status in code:

- No symbol named `CURRICULUM_DEGRADE_MODE` exists in the current long-run code path.
- No `scaffold_ticks_used` field is present in `dependency_debt_state_v1`.
- Existing “scaffold” behavior appears only as routing reasons (`SCAFFOLDING_ALLOWED`) and debt deltas on blocked frontier goals.

Recommended integration point (minimal, compatible extension):

1) Add durable fields to `dependency_debt_state_v1` schema and defaults
- Extend `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`:
  - `curriculum_degrade_mode: string`
  - `scaffold_ticks_used_u64: integer >= 0`
  - `scaffold_ticks_limit_u64: integer >= 0` (or keep this only in profile and copy into state each tick)
- In `_default_dependency_debt_state` and `_load_prev_dependency_debt_state`, initialize/set defaults for these fields.

2) Add config and override sources
- Extend `Genesis/schema/v19_0/long_run_profile_v1.jsonschema` under `dependency_debt`:
  - `curriculum_degrade_mode` (string enum),
  - `base_scaffold_ticks_u64`,
  - `max_scaffold_ticks_u64`.
- Read them in the existing profile block in `microkernel_v1.py` near the `dependency_debt` config extraction.
- Add env override in the same block using `CURRICULUM_DEGRADE_MODE`:
  - `os.environ["CURRICULUM_DEGRADE_MODE"]` style pattern if you want runtime switching,
  - or prefer `long_run_profile_v1` only to keep behavior deterministic.

3) Wire mode into the thresholding function
- In `_forced_frontier_debt_key(...)`, apply per-mode multipliers/scalar adjustments to:
  - `debt_limit_u64`,
  - `max_ticks_without_frontier_attempt_u64`,
  - and scaffold budget.
- This keeps the existing state machine but changes forcing pressure by mode.

4) Count scaffold ticks in the same debt loop
- In the route/build/execute flow where frontier is blocked (`frontier_goals_pending_b and selected_declared_class == "MAINTENANCE"`), increment `scaffold_ticks_used_u64`.
- Reset or freeze it under one of:
  - frontier attempt counted,
  - hard-lock activation/deactivation policy,
  - explicit mode transitions.
- Persist `scaffold_ticks_used_u64` into `dependency_debt_state_v1` every tick.

5) Use scaffold budget to gate hard-lock escalation (or recoveries)
- If `scaffold_ticks_used_u64 >= scaffold_ticks_limit_u64`, trigger early forcing by feeding a lowered effective `max_ticks_without_frontier_attempt_u64` into `_forced_frontier_debt_key`.
- Also emit explicit reason codes (e.g. `CURRICULUM_DEGRADE_MODE_*`, `SCAFFOLD_BUDGET_EXHAUSTED`) in `dependency_routing_receipt_v1.reason_codes`.

6) Expose everything to downstream analysis
- Add corresponding fields to `long_run_tick_index_row_v1` if needed:
  - `curriculum_degrade_mode`,
  - `scaffold_ticks_used_u64`,
  - `scaffold_ticks_limit_u64`.
- Keep `eval_report_v1` references to debt snapshots as-is (`dependency_debt_snapshot_hash`) so all counters are versioned.

## 3.6 Practical implementation notes

- Keep existing defaults unchanged until `CURRICULUM_DEGRADE_MODE` is explicitly set, so historical runs stay behaviorally stable.
- Treat new scaffold counters as additive telemetry first; escalate behavior only once the mode semantics are validated by logs.
- If you need strict backward compatibility, mark new fields optional in schema and make code accept missing keys with defaulting in `_load_prev_dependency_debt_state`.

# 4. The AST / Dependency "Machinery"

## 4.1 What exists today

The AST and touched-path machinery is already implemented in three places:

- `orchestrator/rsi_coordinator_mutator_v1.py`
- `orchestrator/rsi_market_rules_mutator_v1.py`
- `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`

The dependency forcing machinery is implemented in:

- `orchestrator/omega_v19_0/microkernel_v1.py`
- `Genesis/schema/v19_0/dependency_routing_receipt_v1.jsonschema`
- `Genesis/schema/v19_0/dependency_debt_state_v1.jsonschema`
- `Genesis/schema/v18_0/omega_promotion_bundle_ccap_v1.jsonschema`

## 4.2 Patch touched-path machinery (what is currently parsed)

Mutators and axis-gate parsing use the same `+++ b/<path>` extractor.

- They only accept lines that start with `+++ b/`.
- They ignore `+++ /dev/null`.
- They strip surrounding `"quotes"` and normalize separators to `/`.
- They preserve de-duplication order.
- They return `list[str]` of normalized touched paths.

Exact parser output examples:

```text
$ python ...
--- touched coordinator single ['orchestrator/omega_v19_0/coordinator_v1.py']
--- touched coordinator multi ['orchestrator/omega_v19_0/coordinator_v1.py', 'orchestrator/omega_v19_0/other.py']
--- touched market ['orchestrator/omega_v19_0/coordinator_v1.py', 'orchestrator/omega_v19_0/other.py']
--- axis parse ccap patch ['orchestrator/omega_v19_0/coordinator_v1.py']
```

In `CDEL-v2/cdel/v19_0/omega_promoter_v1.py`:

- `_requires_axis_bundle()` calls `_effective_touched_paths_for_axis_gate()`.
- For CCAP bundles (`schema_version == omega_promotion_bundle_ccap_v1`) it reads the patch file path and parses patch headers.
- For non-CCAP bundles it falls back to `extract_touched_paths()` from `CDEL-v2/cdel/v18_0/omega_promotion_bundle_v1.py`.

Axis gate decision output is written to `axis_gate_decision_v1.json` and includes:

- `effective_touched_paths`
- `governed_touched_paths`
- `exempt_relpaths`
- `needs_axis_bundle_b`
- `axis_bundle_present_b`

Observed outputs:

```text
$ python ...
{"axis_bundle_present_b":false,"bundle_schema_version":"omega_promotion_bundle_v1","effective_touched_paths":["docs/readme.md"],"exempt_relpaths":["orchestrator/omega_v19_0/coordinator_v1.py","orchestrator/omega_bid_market_v1.py"],"exemptions_config_id":"sha256:642fe65d716df82045833cecaf624202d90cf7ffd2edd394e7ffe781fe5f7d28","governed_touched_paths":[],"needs_axis_bundle_b":false,"schema_name":"axis_gate_decision_v1","schema_version":"v19_0"}
```

```text
$ python ...
{"axis_bundle_present_b":false,"bundle_schema_version":"omega_promotion_bundle_v1","effective_touched_paths":["orchestrator/omega_v19_0/experimental.py"],"exempt_relpaths":["orchestrator/omega_v19_0/coordinator_v1.py","orchestrator/omega_bid_market_v1.py"],"exemptions_config_id":"sha256:642fe65d716df82045833cecaf624202d90cf7ffd2edd394e7ffe781fe5f7d28","governed_touched_paths":["orchestrator/omega_v19_0/experimental.py"],"needs_axis_bundle_b":true,"schema_name":"axis_gate_decision_v1","schema_version":"v19_0"}
```

The “AST/machine meaningfulness gate” sits directly behind this parser.

## 4.3 AST semantic-change machinery (what counts as meaningful)

Both mutator files expose `_patch_nontrivial_reason`.

- If there are no meaningful diff lines (after removing headers and blank comment lines), it returns `TRIVIAL_PATCH`.
- If full AST diff is unchanged, it returns `TRIVIAL_PATCH`.
- If AST diff with literal normalization is unchanged, it returns `CONSTANTS_ONLY_PATCH`.
- Otherwise it returns `None` (passes as a meaningful change).

Literal normalization uses `_StripLiteralValues`:

- `int/float/complex` -> `0`
- `str` -> `""`
- `bytes` -> `b""`
- `bool` -> `False`
- `None` -> `None`

Observed output:

```text
$ python ...
--- ast constants-only CONSTANTS_ONLY_PATCH
--- ast semantic line None
```

Interpretation:

- `x = 1` -> `x = 2` is intentionally treated as non-meaningful for this gate (`CONSTANTS_ONLY_PATCH`).
- Changing a symbol/operation can pass as meaningful (`None`).

## 4.4 What the dependency machinery currently records

`_pending_frontier_goals` creates rows used by routing and debt machinery.

```text
$ python ...
[{'goal_id': 'g-a', 'capability_id': 'cap-a', 'frontier_id': 'F-A', 'debt_key': 'frontier:F-A'}, {'goal_id': 'g-c', 'capability_id': 'cap-c', 'frontier_id': 'F-C', 'debt_key': 'frontier:F-C'}]
```

`_build_dependency_routing_receipt(...)` outputs this canonical schema:

```text
$ python ...
{'schema_name': 'dependency_routing_receipt_v1', 'schema_version': 'v19_0', 'receipt_id': 'sha256:730ab18115f7addf9c3240445c344b776aefa2bdd8d49550e3a8590ec63fca12', 'tick_u64': 123, 'selected_capability_id': 'orch.cap.capA', 'selected_declared_class': 'MAINTENANCE', 'frontier_goals_pending_b': True, 'blocks_goal_id': 'g-9', 'blocks_debt_key': 'frontier:F-9', 'dependency_debt_delta_i64': 1, 'forced_frontier_attempt_b': False, 'forced_frontier_debt_key': None, 'reason_codes': ['FRONTIER_BLOCKED_BY_PREREQ', 'SCAFFOLDING_ALLOWED']}
```

Default debt state shape from `_default_dependency_debt_state`:

```text
$ python ...
{'schema_name': 'dependency_debt_state_v1', 'schema_version': 'v19_0', 'state_id': 'sha256:0000000000000000000000000000000000000000000000000000000000000000', 'tick_u64': 7, 'debt_by_key': {}, 'ticks_without_frontier_attempt_by_key': {}, 'first_debt_tick_by_key': {}, 'debt_by_goal_id': {}, 'ticks_without_frontier_attempt_by_goal_id': {}, 'first_debt_tick_by_goal_id': {}, 'maintenance_since_last_frontier_attempt_u64': 0, 'last_frontier_attempt_tick_u64': 0, 'last_frontier_attempt_debt_key': None, 'last_frontier_attempt_goal_id': None, 'hard_lock_active_b': False, 'hard_lock_debt_key': None, 'hard_lock_goal_id': None, 'reason_code': 'N/A', 'heavy_ok_count_by_capability': {}, 'heavy_no_utility_count_by_capability': {}, 'maintenance_count_u64': 0, 'frontier_attempts_u64': 0}
```

`dependency_debt_state_v1` persists:

- `debt_by_key`
- `ticks_without_frontier_attempt_by_key`
- `first_debt_tick_by_key`
- `debt_by_goal_id`
- `ticks_without_frontier_attempt_by_goal_id`
- `first_debt_tick_by_goal_id`
- `hard_lock_*`
- `maintenance_*`
- `frontier_attempts_u64` and counters

All of these are written each tick in `orchestrator/omega_v19_0/microkernel_v1.py`.

## 4.5 How a 15-tick scaffolding burst would be represented

The forcing condition is in `_forced_frontier_debt_key(...)`:

```python
debt_u64 >= debt_limit_u64
or (ticks_u64 + 1 + anticipate_without_attempt_u64) >= max_ticks_without_frontier_attempt_u64
```

Current microkernel passes `anticipate_without_attempt_u64=1` when pre-checking forcing.

So for `max_ticks_without_frontier_attempt_u64 = 15` (if configured in profile), a key with 14 accumulated ticks is force-triggered on the next evaluation tick even before evidence of attempted frontier progress.

The same threshold controls both routing behavior and hard-lock activation.

The evidence chain for a scaffold run is visible in:

- `dependency_routing_receipt_v1.reason_codes`
- `dependency_routing_receipt_v1.dependency_debt_delta_i64`
- `dependency_debt_state_v1.ticks_without_frontier_attempt_by_key`
- `dependency_debt_state_v1.debt_by_key`
- `dependency_debt_state_v1.hard_lock_active_b`
- `dependency_routing_receipt_v1.forced_frontier_attempt_b`
- `dependency_routing_receipt_v1.forced_frontier_debt_key`

Representative forcing check output:

```text
$ python ...
frontier:F-8
```

That output came from:

- pending keys `frontier:F-9` and `frontier:F-8`
- debt state with high tick pressure on `frontier:F-8`
- `debt_limit_u64=3`
- `max_ticks_without_frontier_attempt_u64=15`
- `anticipate_without_attempt_u64=1`

Operationally, this means the code will prefer forcing that specific debt key before the next frontier-capable tick completes, which is exactly the machine-readable mechanism behind a “forced scaffolding burst” claim.

To audit a historical run, use these artifacts in order:

- `long_run/debt/dependency_routing_receipt_v1.json`
- `long_run/debt/dependency_debt_state_v1.json`
- `promotion_bundle` / `axis_gate_decision_v1.json` for path governance context
- `axis_bundle` presence and reason outputs when applicable

## 4.6 Summary interpretation

The current system already has an auditable chain for your claim:

- touched files are normalized into deterministic lists
- AST meaningfulness is explicitly filtered before acceptance
- axis governance uses same or compatible touched-path extraction and writes explicit `axis_gate_decision_v1`
- dependency routing writes per-tick receipts and full frontier debt state
- forced attempts are decided from debt keys, debt thresholds, and tick counters via `_forced_frontier_debt_key`
- a 15-tick argument must be validated against `max_ticks_without_frontier_attempt_u64` plus `+1` anticipation in the forcing predicate

