# External Explainer: How This Agent Actually Acts, Learns, Gets Gated, and Fails

This document is written for someone who cannot browse the repository directly.

## 1) Action Space / Tool Schema (How it acts)

### Short answer
The proposer in this stack is **not** a free-form coding agent with arbitrary shell tools. It is mostly a **deterministic patch generator** with a bounded template space, optionally using an LLM only to rank/select from pre-built candidate edits.

### What the proposer can do in one tick
In the current SH-1 proposer path (GE v0.3):
1. Build candidate changes as **unified diffs** (PATCH payloads) against allowed target files.
2. Emit CCAP artifacts (`ccap_v1.json` + patch blob) for verifier/promotion.
3. Optionally use an LLM selector to choose which candidate `(template_id, target_relpath)` pairs to emit.
4. Enter a diagnostic-only mode (emit no CCAPs) when health/fallback conditions trip.

It does **not** expose “run arbitrary bash/unit tests” as an LLM tool call. Test/evaluation execution is handled by orchestrator/verifier stages outside the proposer’s direct tool space.

### Concrete action primitives
The effective action primitives are template-constrained edits, for example:
- `COMMENT_APPEND`
- `CODE_FASTPATH_GUARD`
- `JSON_TWEAK_COOLDOWN(_MINUS_1)`
- `JSON_TWEAK_BUDGET_HINT(_MINUS_1STEP)`

So yes, it outputs unified diffs, but only through deterministic template builders.

### How queue/database injection actually happens
There are two concrete injection pathways:

1. **Patch-based injection into goal/registry artifacts**
- A backlog patch builder can mutate:
  - capability registry (enable capabilities)
  - goal queue (append `PENDING` goals)
- This is merged into emitted CCAP patch bytes.

2. **LLM-router goal injection path (runner-side)**
- `omega_llm_router_v1` returns structured `goal_injections`.
- Runner normalizes and applies each via `_inject_pending_goal(...)` into the goal queue file.

### Implication for degrading `FRONTIER_HEAVY -> FRONTIER_MEDIUM`
Today, `FRONTIER_MEDIUM` is not a recognized declared class in the v19 class set. So a proposer cannot “correctly degrade” by simply writing that label and expecting behavior changes.

What works today:
- Injecting goals/capabilities that route through existing classes (`MAINTENANCE`, `BASELINE_CORE`, `CANARY_HEAVY`, `FRONTIER_HEAVY`).
- Or changing lane/policy/debt configuration so frontier pressure behavior changes without introducing a new class token.

What would be needed for real `FRONTIER_MEDIUM`:
- Add class support in policy schema + class normalization + routing/debt logic + downstream branching.

---

## 2) State-to-Prompt Injection Logic (How it learns)

You currently have **two different “learning surfaces”**:

1. **Deterministic receipt-driven learning (primary)**
2. **LLM prompt payload injection (secondary, bounded)**

### 2.1 Receipt-driven state ingestion (primary loop)
The SH-1 flow ingests recent `ccap_receipt_v1` + refutation certs, builds an experience snapshot (`ge_xs_snapshot_v1`), and derives:
- promotion/rejection stats,
- sentinel/failure class behavior signatures,
- hard-avoid prefixes,
- receipt stream hash fingerprints.

This means failed ticks/verifier outcomes are first-class inputs to next-tick candidate planning, even before any LLM call.

### 2.2 What actually enters the LLM context
For the SH-1 LLM selector, prompt payload is explicit JSON (no hidden template magic):
- `skill_metrics` (normalized metrics)
- `allowed_targets`
- `allowed_templates`
- candidate list (`template_id`, `target_relpath`)
- `max_select`
- required output schema

So the LLM is mostly a constrained ranker/selector, not a free planner.

For `omega_llm_router_v1`, prompt payload includes:
- benchmark gate statuses,
- promotion summary,
- capability usage,
- allowlisted campaign/capability IDs,
- strict limits and required output schema (`web_queries`, `goal_injections`).

### 2.3 How failure is shown to the next tick
- Verifier outcomes are persisted as receipts and consumed by receipt ingestion.
- Episodic memory stores recent outcomes/reason codes and can suppress/demote repeated-failure capabilities.
- LLM side stores prompt/response hashes and tool traces (`ge_prompt_response_hashes_v1`, router plan/trace files), which become part of deterministic run fingerprints.

### 2.4 Your `HEAVY_VALID_*` concern
Your colleague’s idea only works if those reason codes are actively injected into the next prompt payload.

Current state:
- The stack does propagate reason codes in receipts/memory.
- But SH-1 selector prompt does **not** currently include a dedicated heavy-failure reason-code channel (e.g., explicit `HEAVY_VALID_*` instruction block).

So if you want guaranteed behavior shifts in the LLM layer, you need to add explicit prompt fields/instructions derived from those heavy reason codes.

---

## 3) The “J Gate” / Utility Definition (How it’s currently tricked)

There are two relevant gates people conflate:

1. **Objective J dominance gate** (continuity/axis upgrade path)
2. **Heavy utility gate** (promotion path for heavy classes)

### 3.1 Objective J gate (actual math)
`compute_J` builds terms and weighted sum:
- Terms include `UDC_BASE`, `UDC_META`, `INV`, `TDL`, `KDL`, `EDL`, `CDL`, `CoDL`, `IDL`.
- Weighted sum:
  - `lambda*UDC_BASE + mu*UDC_META + nu*INV + alpha*TDL + beta*KDL + gamma*EDL + delta*CDL + eta*CoDL + IDL`

Dominance condition enforced in promoter continuity checks:
- reject if `new_val > (old_val - epsilon)`
- equivalently accepted region is `new_val <= old_val - epsilon`.

There is an extra M_D-specific UDC check:
- require `old_udc - new_udc >= epsilon_udc` (effective epsilon from morphism/constitution).

### 3.2 Heavy utility gate (practical promotion gate)
For `FRONTIER_HEAVY` / `CANARY_HEAVY`, promoter computes utility signals from policy:
- `primary_signal` + threshold
- `stress_signal` + threshold
- examples: `NONTRIVIAL_DELTA`, `WORK_UNITS_REDUCTION`, `REQUIRE_HEALTHCHECK_HASH`, `REQUIRE_PATCH_DELTA`, etc.

If heavy utility fails:
- promotion becomes `SKIPPED`
- reason code `NO_UTILITY_GAIN_SHADOW`
- effect class `EFFECT_HEAVY_NO_UTILITY`
- utility proof receipt is written with metrics/thresholds.

### 3.3 Why this can be Goodharted
If policy signal is shallow (for example binary nontrivial delta), the system can optimize toward passing that signal without meaningful capability gain.

So your anti-Goodhart fix should target:
- signal definition (`primary_signal`, `stress_signal`),
- baseline comparison integrity,
- and coupling between signal pass and downstream real performance evidence.

---

## 4) One Concrete Failure Trace (~200 ticks)

Run used: `runs/mission_replay_200_v1`

### 4.1 Target context (frontier-heavy ground truth)
At tick 200, mission ingestion accepted a frontier lane payload with goals including:
- `RSI_KNOWLEDGE_TRANSPILER`
- `RSI_OMEGA_NATIVE_MODULE`

In the active utility policy, both are declared `FRONTIER_HEAVY`.

So this is a valid frontier-heavy target context at ~200 ticks.

### 4.2 What happened near the end
From final index rows (ticks 197–200):
- tick 197: `lane=BASELINE`, `status=ERROR`, `state_verifier_reason_code=TICK_PROCESS_ERROR`
- tick 198: same
- tick 199: same
- tick 200: lane flips to `FRONTIER`, but still `status=ERROR`, same verifier reason

Repeated stderr tail on those ticks points to schema/event mismatch involving `DEPENDENCY_ROUTING` and `SAFE_HALT` expectation.

### 4.3 Tick-200 routing internals
Tick 200 dependency routing receipt:
- `selected_capability_id = RSI_GE_SH1_OPTIMIZER`
- `selected_declared_class = MAINTENANCE`
- `frontier_goals_pending_b = true`
- `forced_frontier_attempt_b = false`
- reason codes:
  - `FRONTIER_BLOCKED_BY_PREREQ`
  - `SCAFFOLDING_ALLOWED`

This is the failure shape:
- Frontier-heavy goals are present,
- but execution keeps routing to maintenance/scaffolding,
- and the run hard-fails repeatedly at verifier/state-event boundary (schema-level failure), creating a loop.

### 4.4 Why this trace is useful
It shows the system is not merely writing bad code; it is caught in a **control-plane/schema loop**:
- frontier pressure exists,
- frontier attempt not counted,
- routing reason repeats,
- tick verifier keeps erroring on event handling.

That is a stronger diagnosis than “LLM wrote boilerplate.”

---

## Direct answers to your four asks

1. **Action space/tool schema**: bounded patch templates + optional constrained LLM selection; no arbitrary bash/test tool calls from proposer.
2. **State-to-prompt logic**: receipt-driven memory is primary; LLM prompt payloads are explicit JSON with bounded fields; heavy reason-code steering is not fully explicit yet.
3. **J gate / utility definition**: Objective J weighted formula + dominance inequality; separate heavy utility signal gate in promoter controls heavy-class promotion shadowing.
4. **Concrete failure trace**: `mission_replay_200_v1`, frontier-heavy goals at tick 200, final 4 ticks stuck in `TICK_PROCESS_ERROR` with dependency-routing/scaffolding pattern.

