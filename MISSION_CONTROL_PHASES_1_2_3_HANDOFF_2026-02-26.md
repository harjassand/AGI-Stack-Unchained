# Mission Control Phases 1-3 Handoff (Detailed)

## Scope
- Audience: engineers who do not have direct access to this repository.
- Goal: document exactly what was implemented in Phase 1, Phase 2, and Phase 3 during the last 2 hours.
- Time window covered: Thursday, February 26, 2026 (local commit timezone `+1000`), approximately `23:03:37` to `23:36:10`.
- Repository root analyzed: `/Users/harjas/AGI-Stack-Unchained`.

## Source-of-Truth Timeline (Exact Commits)
1. `2d9879a` at `2026-02-26 23:03:37 +1000`  
   Subject: `mc(phase2): add fastapi sse stream server and state endpoint`  
   PR merge commit later: `9d71d0c` (`Merge pull request #12 from harjassand/mc/phase2-stream`) at `23:30:39 +1000`.
2. `4070d0f` at `2026-02-26 23:32:30 +1000`  
   Subject: `mc(phase1): add nlpmc mission compiler with schema validation`  
   PR merge commit later: `9dc59b5` (`Merge pull request #13 from harjassand/codex/mc-phase1-nlpmc`) at `23:33:17 +1000`.
3. `5e9e180` at `2026-02-26 23:35:26 +1000`  
   Subject: `mc(phase3): add nextjs dashboard with sse monologue and dag`  
   PR merge commit later: `25373d0` (`Merge pull request #14 from harjassand/codex/mc-phase3-ui`) at `23:36:10 +1000`.

Note: implementation commit order was Phase 2 -> Phase 1 -> Phase 3 (not strictly numeric order by time).

## Change Volume Summary
- Phase 1 (`4070d0f`): `1 file`, `398 insertions`
- Phase 2 (`2d9879a`): `3 files`, `350 insertions`
- Phase 3 (`5e9e180`): `17 files`, `7476 insertions`
  - Of the Phase 3 lines, `6548` are in `package-lock.json` (generated dependency lockfile).

## Files Added Per Phase

### Phase 1
- `tools/mission_control/nlpmc_v1.py`

### Phase 2
- `tools/mission_control/_signal_parse_v1.py`
- `tools/mission_control/_state_discovery_v1.py`
- `tools/mission_control/stream_server_v1.py`

### Phase 3
- `mission-control-ui/.gitignore`
- `mission-control-ui/README.md`
- `mission-control-ui/app/favicon.ico`
- `mission-control-ui/app/globals.css`
- `mission-control-ui/app/layout.tsx`
- `mission-control-ui/app/page.tsx`
- `mission-control-ui/eslint.config.mjs`
- `mission-control-ui/next.config.ts`
- `mission-control-ui/package-lock.json`
- `mission-control-ui/package.json`
- `mission-control-ui/postcss.config.mjs`
- `mission-control-ui/public/file.svg`
- `mission-control-ui/public/globe.svg`
- `mission-control-ui/public/next.svg`
- `mission-control-ui/public/vercel.svg`
- `mission-control-ui/public/window.svg`
- `mission-control-ui/tsconfig.json`

---

## End-to-End System Intent Across Phases
This 3-phase implementation creates a local Mission Control vertical slice:
1. Compile mission intent into schema-valid staged mission JSON (Phase 1).
2. Serve telemetry/state/mission ingest via FastAPI + SSE (Phase 2).
3. Render a live operator UI in Next.js that consumes those APIs (Phase 3).

In practical terms:
- UI posts mission text to `POST /api/mission`.
- Backend attempts to invoke `compile_and_stage_mission(...)`.
- Backend streams live log-derived events via `GET /stream`.
- UI polls `GET /api/state/current` once per second.
- UI builds a live monologue and DAG from the SSE stream.

---

## Phase 1 Deep Dive: NLPMC Mission Compiler (`nlpmc_v1.py`)

## Primary Responsibility
Translate freeform human mission intent into a validated `mission_request_v1` payload, compute deterministic `mission_id`, and atomically stage it to disk.

## Main Entry Point
`compile_and_stage_mission(human_intent_str, repo_root=".", max_retries=3, staging_relpath=".omega_cache/mission_staging/pending_mission.json") -> dict`

Return shape:
```json
{
  "mission_id": "sha256:<hex>",
  "payload": { "...": "mission payload" },
  "staged_path": ".omega_cache/mission_staging/pending_mission.json"
}
```

## Core Algorithm
1. Resolve and load required JSON inputs:
   - Schema: `Genesis/schema/v19_0/mission_request_v1.jsonschema`
   - Capability registry: `campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json`
2. Build system prompt by concatenating:
   - fixed header string
   - minified schema JSON
   - minified capability registry JSON
3. Validate non-empty human intent.
4. Retry generation up to `max_retries`, with temperatures sequence:
   - Attempt 1: `0.0`
   - Attempt 2: `0.2`
   - Attempt 3+: `0.4`
5. Parse model output strictly as a single JSON object (no trailing text).
6. Force schema constants if present:
   - `schema_name`
   - `schema_version`
7. Echo `human_intent_str` into payload if schema includes that property.
8. Compute deterministic `mission_id`:
   - clone payload and remove `mission_id`
   - canonicalize with CDEL canon bytes
   - hash with SHA-256 and prefix with `sha256:`
9. Include `mission_id` only if schema allows the field (`properties` or permissive `additionalProperties`).
10. Validate payload with CDEL validator (`validate_schema_v19(payload, "mission_request_v1")`) under temporary `OMEGA_REPO_ROOT`.
11. Atomically stage canonical bytes:
   - write temp file
   - `fsync(file)`
   - `os.replace(temp, target)`
   - `fsync(parent_dir_fd)`
12. Return mission metadata.

## LLM Backend Behavior
- Backend is hard-gated to MLX:
  - `ORCH_LLM_BACKEND` must be `"mlx"` or compiler raises `NLPMC_NOT_AVAILABLE`.
- Default model:
  - `mlx-community/Qwen2.5-Coder-14B-Instruct-4bit`
- Prompt rendering:
  - Uses tokenizer `apply_chat_template(...)` when available.
  - Falls back to raw string concatenation.
- Determinism:
  - Seed derived from `ORCH_LLM_SEED_U64` or `OMEGA_RUN_SEED_U64` (modulo `2^64`) and attempt index.

## Phase 1 Environment Variables
- `ORCH_LLM_BACKEND` (required to be `mlx`)
- `ORCH_MLX_MODEL` (optional override)
- `ORCH_MLX_REVISION` (optional)
- `ORCH_MLX_ADAPTER_PATH` (optional)
- `ORCH_LLM_MAX_TOKENS` (default `4096`)
- `ORCH_LLM_TOP_P` (default `0.95`, clamped `0..1`)
- `ORCH_LLM_SEED_U64` (optional)
- `OMEGA_RUN_SEED_U64` (optional fallback seed)
- `OMEGA_REPO_ROOT` (set transiently during validation)

## Error Contract (Stable Prefixes Used)
- `NLPMC_SCHEMA_NOT_FOUND`
- `NLPMC_CAPREG_NOT_FOUND`
- `NLPMC_EMPTY_INTENT`
- `NLPMC_JSON_PARSE_FAILED`
- `NLPMC_NOT_AVAILABLE`
- `NLPMC_VALIDATION_FAILED` (final wrapper on failures after retry loop)

## Key Implementation Notes
- Canonical serialization and hashing are done through CDEL functions (`cdel.v1_7r.canon.canon_bytes`).
- Temp file naming includes process id.
- Backend `close()` explicitly clears MLX model cache and attempts `mx.metal.clear_cache()`.

---

## Phase 2 Deep Dive: FastAPI Stream + State Server

Files:
- `_signal_parse_v1.py`
- `_state_discovery_v1.py`
- `stream_server_v1.py`

## Public API Contract

### `GET /stream`
- Content type: `text/event-stream`
- Source: tail of runaway log file
- Event payload fields:
  - `ts_unix_ms`
  - `seq` (incremental integer per emitted event)
  - `trace_class` (`REASONING`, `EXECUTION`, `VERIFICATION`, `GOVERNANCE`, etc.)
  - `signal`
  - `tick_u64`
  - `raw_line`
  - `fields` (tokenized `key=value` map)

### `GET /api/state/current`
- Returns:
```json
{
  "ts_unix_ms": 0,
  "omega_state": { "...": "latest discovered omega state or null" },
  "active_bundle": {
    "active_bundle_relpath": "meta-core/active/ACTIVE_BUNDLE",
    "active_bundle_value": ""
  },
  "host": {
    "rss_bytes": 0,
    "vms_bytes": 0,
    "cpu_pct": 0.0
  }
}
```

### `POST /api/mission`
Request:
```json
{ "human_intent_str": "..." }
```

Response (success):
```json
{
  "ok": true,
  "mission_id": "sha256:...",
  "staged_path": ".omega_cache/mission_staging/pending_mission.json"
}
```

Response when compiler not importable:
```json
{
  "ok": false,
  "error": "NLPMC_NOT_AVAILABLE"
}
```
HTTP status for not-available case: `501`.

## SSE Log Discovery Rules
Log source selection checks, in order:
1. `MC_RUNAWAY_LOG_PATH` if set and valid file.
2. `<repo>/runaway_evolution.log`
3. `<repo>/runs/runaway_evolution.log`

If no log exists:
- emits synthetic `LOG_NOT_FOUND` event every 2 seconds.

Tail semantics:
- opens selected file
- seeks to EOF on connect/switch
- emits only new appended lines (no historical replay on connect)

## Signal Parsing and Classification
`parse_signal_line` logic:
- ignores lines without `SIGNAL=`
- splits line by whitespace into tokens
- collects `key=value` pairs
- parses tick from `TICK` or `tick_u64`, fallback `0`

`map_trace_class` categories:
- `VERIFICATION`: exact signals (`CCAP_DECISION`, etc.) or prefix `PROOF_`
- `EXECUTION`: exact (`REWRITE_ATTEMPT`, etc.) or prefixes `CAMPAIGN_`, `NATIVE_`
- `REASONING`: exact (`VOID_SCORE`, `PATCH_GEN`) or prefixes `POLYMATH_`, `LLM_`
- `GOVERNANCE`: governance exact set and default fallback

## State Discovery Rules
`discover_state_path`:
- first: `MC_STATE_PATH` (if file exists)
- otherwise: newest mtime match of `daemon/*/state/omega_state_v1.json`

`read_active_bundle`:
- reads `meta-core/active/ACTIVE_BUNDLE` as string if present

`host_metrics`:
- uses `psutil` when importable
- returns zeros when unavailable or error

## Mission Endpoint Dispatch Logic
1. Dynamic import `tools.mission_control.nlpmc_v1`.
2. Resolve callable `compile_and_stage_mission`.
3. Invoke with keyword arg; fallback to positional on `TypeError`.
4. If return is awaitable, await it.
5. Normalize mission id:
   - dict return: read `mission_id`, `staged_path`
   - string return: treat as mission id
   - fallback if missing mission id: deterministic sha256 of input intent

## Backend Runtime and CORS
- App title: `Mission Control Stream Server v1`
- CORS allow origins:
  - `http://127.0.0.1:3000`
  - `http://localhost:3000`
- Run entrypoint (`main()`):
  - host `127.0.0.1`
  - port `7890`

---

## Phase 3 Deep Dive: Next.js Mission Control Dashboard

Directory: `mission-control-ui/`

## Tech Stack
- Next.js `16.1.6` (App Router)
- React `19.2.3`
- TypeScript strict mode
- Tailwind CSS v4
- `framer-motion` animations
- `reactflow` DAG rendering

## Environment and Defaults
- Server base env variable: `NEXT_PUBLIC_MC_SERVER_BASE`
- Default base URL: `http://127.0.0.1:7890`
- UI dev server bind: `127.0.0.1:3000`

## Screen Composition (Single Main Page)
Three-panel layout:
1. Left: command console, goal queue buckets, host health.
2. Center: live monologue stream + signal DAG.
3. Right: active bundle value + latest important artifact payload.

## Runtime Data Flows

### Mission Submission
- Form posts `{ human_intent_str }` to `/api/mission`.
- Feedback text shows mission id + staged path or error.

### State Polling
- Fetches `/api/state/current` every `1000ms` with `cache: "no-store"`.
- Extracts `omega_state.goal_queue`.
- Normalizes into buckets:
  - `pending`
  - `active`
  - `completed`

### SSE Subscription
- Opens `EventSource(<base>/stream)`.
- On each message:
  - parses JSON
  - deduplicates by `seq` using `Set`
  - normalizes fields and appends event
- Reconnect behavior:
  - on error: closes source
  - sets UI warning
  - retries in `1s`

## In-Memory Event and DAG Strategy
- Keeps up to ~400 events:
  - `setStreamEvents((prev) => [...prev.slice(-399), incoming])`
- Tracks latest important artifact when signal is:
  - `ACTIVATION_COMMIT`
  - `CCAP_DECISION`
- DAG node identity:
  - key = `signal` + optional `capability`/`domain`
- DAG edges:
  - connects sequential nodes sharing same `tick_u64`
  - edge ids deduplicated with a `Set`

## Visual and Theming Notes
- Custom font pairing:
  - `Space_Grotesk`
  - `IBM_Plex_Mono`
- Background:
  - radial gradient over dark blue slate palette
- ReactFlow styles customized for controls and minimap surfaces.

## Added Project Config
- `next.config.ts` with turbopack root set to `process.cwd()`.
- ESLint config uses `eslint-config-next/core-web-vitals` + TypeScript.
- Tailwind PostCSS plugin wired.
- Standard Next.js `.gitignore` plus env/build ignores.

---

## Integration Map (How Phases Connect)
1. Phase 3 UI mission form -> Phase 2 `POST /api/mission`.
2. Phase 2 mission endpoint -> Phase 1 `compile_and_stage_mission`.
3. Phase 3 UI stream panel -> Phase 2 `GET /stream`.
4. Phase 3 UI state widgets -> Phase 2 `GET /api/state/current`.

Data handoff path for mission payload:
- UI input string -> backend compiler -> canonical payload -> staged file:
  `.omega_cache/mission_staging/pending_mission.json`

---

## Operational Runbook (Local)

## Backend (Phase 2 + Phase 1)
```bash
cd /Users/harjas/AGI-Stack-Unchained
python3 -m pip install -r tools/mission_control/requirements.txt
python3 tools/mission_control/stream_server_v1.py
```
Expected bind: `http://127.0.0.1:7890`.

## UI (Phase 3)
```bash
cd /Users/harjas/AGI-Stack-Unchained/mission-control-ui
npm install
npm run dev
```
Expected bind: `http://127.0.0.1:3000`.

Optional override:
```bash
echo 'NEXT_PUBLIC_MC_SERVER_BASE=http://127.0.0.1:7890' > .env.local
```

---

## Validation Performed During This Handoff
- Python syntax check executed successfully:
  - `tools/mission_control/nlpmc_v1.py`
  - `tools/mission_control/_signal_parse_v1.py`
  - `tools/mission_control/_state_discovery_v1.py`
  - `tools/mission_control/stream_server_v1.py`
- UI dependency install/lint/build not run in this pass because `mission-control-ui/node_modules` was not present at inspection time.

---

## Known Gaps, Risks, and Follow-Up Priorities

## P0/P1 Operational Risks
1. No automated tests were added for new Phase 1/2/3 code in these commits.
2. `POST /api/mission` does not wrap compiler exceptions into stable HTTP error schema; uncaught runtime errors may surface as generic 500s.
3. SSE parser is whitespace-token-based and will not preserve values containing spaces unless encoded without spaces in log lines.
4. SSE tail starts at EOF, so dashboard does not replay historical events on first connect.

## P2 Design/Integration Gaps
1. New stack (`tools/mission_control/*_v1.py` + `mission-control-ui`) is adjacent to, not integrated into, legacy `tools/mission_control/mission_control/` server package.
2. `trust_remote_code` is parsed in NLPMC backend but not passed into model load kwargs (currently inert config).
3. In-memory sets/maps in UI (seen seq, DAG node keys, tick maps, edge set) grow for session lifetime; no pruning strategy.
4. CORS is hard-coded to localhost origins only.
5. No authN/authZ is present on backend endpoints (local-trust model only).

## P3 Hardening Opportunities
1. Add contract tests for:
   - mission compiler schema/const enforcement
   - mission id determinism
   - SSE event schema and parsing edge cases
   - `/api/state/current` fallback behaviors
2. Add health/readiness endpoint and structured logging on backend.
3. Add UI e2e checks for reconnect, dedupe, and DAG growth behavior.
4. Add replay/backfill option for SSE startup.

---

## Quick Reference: New API/Function Surfaces

## Python
- `tools.mission_control.nlpmc_v1.compile_and_stage_mission(...)`
- `tools.mission_control._signal_parse_v1.parse_signal_line(...)`
- `tools.mission_control._signal_parse_v1.map_trace_class(...)`
- `tools.mission_control._state_discovery_v1.build_current_state_payload(...)`
- FastAPI app in `tools.mission_control.stream_server_v1:app`

## HTTP
- `GET /stream`
- `GET /api/state/current`
- `POST /api/mission`

## UI Env
- `NEXT_PUBLIC_MC_SERVER_BASE`

---

## Handoff Bottom Line
In the last ~33 minutes of commits (`23:03` to `23:36` on February 26, 2026 +1000), the project gained a complete Mission Control operator path:
- mission intent compiler with schema validation and atomic staging,
- live telemetry/state FastAPI service with SSE,
- and a new Next.js dashboard consuming both.

The implementation is functionally cohesive, but currently in "first operational slice" quality level: strong scaffolding and clear contracts, with testing/hardening/integration work still pending.
