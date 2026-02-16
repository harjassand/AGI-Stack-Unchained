## Phase U-2.3 Directive: Iteration + Expansion (Legacy Skills + Live LLM + Polymath Targeting + Dataset Refresh Hooks)

### Non-negotiables

* **No new trust / no new governance / no new acceptance paths.**
* LLM outputs remain **untrusted** and must be **receipt-/replay-backed** to satisfy determinism.
* All new “legacy skills” remain **analysis-only**: they produce `omega_skill_report_v1` artifacts and influence scheduling only via untrusted goal overlays (or GE ranking), never via direct promotion authority.

---

# 1) Expand legacy skills (adapters + campaigns + observer wiring)

You already have the OLSA pattern:

* `omega_skill_report_v1` schema
* `skill_runner_v1.py` and adapters
* analysis-only campaigns writing `skills/reports/<skill>/omega_skill_report_v1.json`
* observer + verifier reading those fixed paths into normalized metrics

U-2.3 extends that same mechanism to:

* v7.0 alignment → `alignment_q32`
* v8 boundless math → novelty + throughput metrics
* v9 boundless science → novelty + throughput metrics
* v3.x swarm coordination → `swarm_coordination_q32`
* v10 model genesis → dataset refresh/bias proxies

### 1.1 Add new skill IDs + fixed paths (no new schema family)

**Add these entries** to the skill-source table in `cdel/v18_0/omega_observer_v1.py` (and mirror in verifier source resolution in `verify_rsi_omega_daemon_v1.py`):

| Skill             | schema_id                                 | report relpath                                                | producer campaign_id                   | metric keys                                                                           |
| ----------------- | ----------------------------------------- | ------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------- |
| v7 alignment      | `omega_skill_alignment_report_v1`         | `skills/reports/alignment/omega_skill_report_v1.json`         | `rsi_omega_skill_alignment_v1`         | `alignment_q32`, `alignment_flags_u64`                                                |
| v8 math           | `omega_skill_boundless_math_report_v1`    | `skills/reports/boundless_math/omega_skill_report_v1.json`    | `rsi_omega_skill_boundless_math_v1`    | `math_novelty_q32`, `math_attempts_u64`, `math_success_rate_rat`                      |
| v9 science        | `omega_skill_boundless_science_report_v1` | `skills/reports/boundless_science/omega_skill_report_v1.json` | `rsi_omega_skill_boundless_science_v1` | `science_novelty_q32`, `science_attempts_u64`, `science_success_rate_rat`             |
| v3 swarm          | `omega_skill_swarm_report_v1`             | `skills/reports/swarm/omega_skill_report_v1.json`             | `rsi_omega_skill_swarm_v1`             | `swarm_coordination_q32`, `swarm_faults_u64`                                          |
| v10 model genesis | `omega_skill_model_genesis_report_v1`     | `skills/reports/model_genesis/omega_skill_report_v1.json`     | `rsi_omega_skill_model_genesis_v1`     | `dataset_balance_q32`, `dataset_refresh_needed_b_q32`, `model_genesis_last_model_u64` |

**Observer wiring requirements**

* Add these metrics to:

  * `metrics` map (q32 objects + u64 ints + rat objects)
  * `metric_series` (same)
* Fail-closed behavior: if a report exists but schema/fields invalid → `SCHEMA_FAIL`.

### 1.2 Implement adapters (CDEL-v2, analysis-only)

Add adapter modules under `cdel/v18_0/skills/`:

1. `alignment_v7_adapter_v1.py`
2. `boundless_math_v8_adapter_v1.py`
3. `boundless_science_v9_adapter_v1.py`
4. `swarm_v3_adapter_v1.py`
5. `model_genesis_v10_adapter_v1.py`

**All adapters must implement:**

```python
def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    # returns omega_skill_report_v1 payload
```

#### Adapter metric definitions (exact)

* `alignment_q32`: 1.0 if latest v7 alignment run indicates pass, else 0.0.

  * Sources: scan for latest artifact under `runs/**/rsi_alignment_v7_0/**` or `daemon/rsi_daemon_v7_0/**`.
  * If no artifacts exist → set `alignment_q32=0` and add flag `NO_ALIGNMENT_ARTIFACTS`.

* `math_novelty_q32`: novelty coverage over last N attempts:

  * define attempt ID extraction as the set of unique `attempt_id` (or equivalent) in the v8 ledger JSONL.
  * novelty = unique_attempt_ids / total_attempts over window; q32 ratio.
  * If ledger absent → `math_novelty_q32=0`, flag `NO_MATH_LEDGER`.

* `science_novelty_q32`: same but from v9 ledger / attempt receipts.

* `swarm_coordination_q32`:

  * If swarm ledger exists: `1 - (faults/total_events)` over last N events.
  * Faults defined as any entry with missing predecessor hash, invalid cross-ledger ref, or verifier error tags present in row.
  * If no ledger: flag `NO_SWARM_LEDGER`.

* `dataset_balance_q32`:

  * Load latest v10 training corpus manifest.
  * If a histogram exists (class/token/source buckets), compute min(bucket)/max(bucket) ratio as q32.
  * If not present: fall back to `1.0` and flag `NO_BALANCE_HISTOGRAM`.
  * `dataset_refresh_needed_b_q32`: set to 1.0 if balance < threshold (threshold pinned in adapter constant, default 0.6), else 0.

### 1.3 Add analysis-only campaigns and packs (CDEL-v2 + AGI-Stack)

For each new skill:

* `campaign_omega_skill_alignment_v1.py`
* `campaign_omega_skill_boundless_math_v1.py`
* `campaign_omega_skill_boundless_science_v1.py`
* `campaign_omega_skill_swarm_v1.py`
* `campaign_omega_skill_model_genesis_v1.py`

Each campaign:

* Runs `skill_runner_v1.py --skill_id <...> --out_dir <subrun_out_dir>/skills/reports/<skill>/`
* Writes the canonical report at:

  * `skills/reports/<skill>/omega_skill_report_v1.json`
* Produces **no promotion bundle** (analysis-only).

Add campaign packs under `campaigns/rsi_omega_skill_<skill>_v1/`.

Add capability registry rows (disabled by default) in both prod/non-prod omega registries.

---

# 2) Integrate live LLM backends (OpenAI + Anthropic) for GE proposal selection — determinism-preserving

You currently have only `mock` and `replay` in `harjassand/agi-orchestrator/orchestrator/llm_backend.py`. Add live providers **but do it in a way that preserves SH-0/SH-1 determinism**:

### 2.1 Two-mode policy (required)

* **replay-only mode (default):** deterministic; fails closed if replay lacks an entry.
* **harvest mode (explicit):** allows live calls and appends prompt/response pairs to the replay file. Must require an explicit env toggle.

This is the only safe way to use live models while keeping CCAP submission deterministic (C1).

### 2.2 Implement OpenAI backend (agi-orchestrator)

**File:** `orchestrator/llm_backend.py` (in `harjassand/agi-orchestrator`)

Add backend names:

* `openai_replay` (replay-only but validates OPENAI model id)
* `openai_harvest` (live + append-to-replay)

Implement HTTP call using OpenAI **Responses** endpoint: `POST https://api.openai.com/v1/responses` with Bearer auth. ([OpenAI Platform][1])
Use model IDs supported by Responses. ([OpenAI Platform][2])

Env vars:

* `OPENAI_API_KEY` (required for harvest)
* `ORCH_OPENAI_MODEL` (default `gpt-4.1` or `gpt-5` depending on your preference)
* `ORCH_LLM_REPLAY_PATH` (required for both replay and harvest)
* `ORCH_LLM_LIVE_OK=1` must be set to allow harvest (otherwise fail closed)

Response parsing:

* Extract the assistant text from the response output; store raw JSON in the replay log too.

### 2.3 Implement Anthropic backend (agi-orchestrator)

Add:

* `anthropic_replay`
* `anthropic_harvest`

Anthropic Messages API: `POST https://api.anthropic.com/v1/messages` with required headers `x-api-key`, `anthropic-version`. ([Claude API Docs][3])

Env vars:

* `ANTHROPIC_API_KEY`
* `ORCH_ANTHROPIC_MODEL` (default per your choice)
* `ORCH_ANTHROPIC_VERSION` (default `2023-06-01`)
* `ORCH_LLM_REPLAY_PATH`
* `ORCH_LLM_LIVE_OK=1` for harvest

### 2.4 Replay log format (pinned, deterministic)

Write JSONL entries:

```json
{
  "schema_version":"orch_llm_replay_row_v1",
  "backend":"openai|anthropic",
  "model":"...",
  "prompt_sha256":"sha256:...",
  "response_sha256":"sha256:...",
  "prompt":"<exact>",
  "response":"<exact>",
  "created_at_utc":"..."
}
```

Replay lookup key:

* `(backend, model, prompt_sha256)` must match exactly.

### 2.5 Wire GE to use LLM for **selection only** (not patch generation)

**File:** `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`

Add optional config section to `ge_config_v1.jsonschema` + config:

```json
"llm_selector": {
  "enabled_b": true,
  "backend": "openai_replay|openai_harvest|anthropic_replay|anthropic_harvest",
  "model": "string",
  "max_proposals_u64": 8
}
```

Behavior:

* GE still uses **deterministic templates** to generate patch bytes.
* LLM only selects `(template_id, target_relpath)` from an enumerated candidate list.
* GE builds one prompt containing:

  * current normalized skill metrics
  * list of allowed targets
  * list of allowed templates
  * required output: JSON list of selections
* GE records prompt/response hashes in `ge_prompt_response_hashes_v1.json` and includes them in `ge_run_inputs_fingerprint_v2.json`.

Fail-closed:

* If selector enabled and backend is replay but no entry exists → GE emits `diagnostic_only_b=true` and writes `ge_diagnostic_only_v1.json` with reason `LLM_REPLAY_MISS`.

**Note on “ChatGPT Pro membership”**
ChatGPT Pro is separate from API access. For OpenAI/Anthropic live calls you still need API keys + billing on the provider side. (This is an operational note; implementation uses env vars.)

---

# 3) Enhance Polymath for targeted discoveries (void → boundless math/science goal injection)

Goal: turn scout voids into **concrete math/science work**.

### 3.1 Add a deterministic void→goal scheduler (run-local, not repo-dirty)

Implement `tools/polymath/polymath_void_to_goals_v1.py` (AGI-Stack).

Inputs:

* `--void_report_path` (default `polymath/registry/polymath_void_report_v1.jsonl`)
* `--out_goal_queue_effective_path` (path inside run overlay pack, e.g. `<run_dir>/_overnight_pack/goals/omega_goal_queue_effective_v1.json`)
* `--max_goals` (default 2)
* `--tick_u64` (used only for deterministic goal_id suffix)

Rules:

1. Read void report, choose top K by `void_score_q32.q` (tie-break: `topic_id`).
2. Map topic → `MATH` or `SCIENCE` via pinned rules in a committed file:

   * `polymath/registry/void_topic_router_v1.json`
3. Emit PENDING goals into effective queue for:

   * `RSI_BOUNDLESS_MATH_V8`
   * `RSI_BOUNDLESS_SCIENCE_V9`
4. Goal IDs must be deterministic:

   * `goal_auto_00_void_math_<topic_id>_<tick_u64:04d>`
   * `goal_auto_00_void_science_<topic_id>_<tick_u64:04d>`
5. Do not duplicate existing pending goals for same topic_id.

### 3.2 Wire scheduler into overnight runner

**File:** `tools/omega/omega_overnight_runner_v1.py`

When `--enable_polymath_drive 1`:

* After each scout (at pre-loop and at each checkpoint), call `polymath_void_to_goals_v1.py` targeting the overlay pack’s `goals/omega_goal_queue_effective_v1.json`.

Add artifact:

* `OMEGA_VOID_TO_GOALS_REPORT_v1.json` in run_dir summarizing injected goals.

---

# 4) Refresh datasets/models via v10 model genesis (bias reduction hook)

This is not “train big models” yet; it’s “wire the pipeline + metrics.”

### 4.1 Enable v10 campaign in unified profile (disabled by default elsewhere)

Add capability row for `rsi_model_genesis_v10_0` in omega registries (if not present) and enable it only in `profile=unified` overlay.

### 4.2 Add a simple scheduler rule (untrusted) based on the new v10 skill metric

In GE policy steering:

* If `dataset_refresh_needed_b_q32 == 1.0`, bias the bucket plan toward `grow` and prioritize model genesis goals.

---

# 5) Plan U-2.4 scaffolding (do now, implement later)

Add a placeholder design doc (no runtime changes):

* `docs/phase_u2_4_swarm_scaling_plan.md`
  Include:
* distributed run orchestration via swarm runners
* failure analysis: automatic summarization from run artifacts (no new trust)

---

# 6) Tests and acceptance criteria

## 6.1 New tests (must add)

1. `test_legacy_skill_alignment_v7_report_v1.py`
2. `test_legacy_skill_boundless_math_v8_report_v1.py`
3. `test_legacy_skill_boundless_science_v9_report_v1.py`
4. `test_legacy_skill_swarm_v3_report_v1.py`
5. `test_legacy_skill_model_genesis_v10_report_v1.py`

Each test should:

* create a minimal fake run subtree in `tmp_path/runs/...` with one representative artifact
* run `skill_runner_v1.py`
* assert report schema valid and observer ingests metric.

6. `agi-orchestrator` tests:

* `test_llm_backend_replay_miss_fails_closed.py`
* `test_llm_backend_harvest_appends_replay.py` (mock HTTP)

7. `ge` tests:

* `test_ge_llm_selector_replay_path_v1.py` (replay selection determinism)

## 6.2 Acceptance runs

* **D2 stable** remains true (verifier VALID; no nondeterminism regressions).
* U-2.3 success criteria:

  1. In unified profile 30-minute run, at least one skill report exists for v7/v8/v9/v10/v3 adapters.
  2. GE can run with LLM selector in replay mode deterministically.
  3. Polymath void-to-goals produces at least one boundless math or science dispatch.

---

## Implementation note on OpenAI + Anthropic endpoints

OpenAI: use Responses endpoint `/v1/responses` for new integration. ([OpenAI Platform][1])
Anthropic: use Messages API `/v1/messages` with `anthropic-version` header. ([Claude API Docs][3])

This completes Phase U-2.3: expanded legacy skills, live LLM integration in a determinism-safe way, polymath targeted discoveries, and model genesis refresh hooks—without adding any new trust or governance surfaces.

[1]: https://platform.openai.com/docs/api-reference/responses/list?utm_source=chatgpt.com "Responses | OpenAI API Reference"
[2]: https://platform.openai.com/docs/models/gpt-5.1-codex-max?utm_source=chatgpt.com "GPT-5.1-Codex-Max Model | OpenAI API"
[3]: https://docs.anthropic.com/zh-TW/api/messages?utm_source=chatgpt.com "訊息 - Anthropic"
