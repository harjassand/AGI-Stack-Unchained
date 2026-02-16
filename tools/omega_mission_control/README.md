# Omega Mission Control (Next.js) v18.0

Standalone React/Next.js replacement for legacy `tools/mission_control`, with a single Node process that serves:

- Next.js App Router UI
- WebSocket stream at `/ws`
- REST API under `/api/v1/*`

It reads Omega Daemon v18.0 run artifacts from disk in `fs` mode, and in `mock` mode it generates deterministic synthetic artifacts in the same on-disk structure.

## Quick Start

```bash
cd tools/omega_mission_control
npm ci
npm run dev -- --repo_root /ABS/PATH/TO/REPO --runs_root /ABS/PATH/TO/RUNS --mode mock
```

Then open `http://localhost:3000`.

## Config

Required:

- `OMEGA_MC_MODE=mock|fs`
- `OMEGA_MC_RUNS_ROOT=<abs_path>`
- `OMEGA_MC_REPO_ROOT=<abs_path>`

CLI flags override env values:

- `--mode`
- `--runs_root`
- `--repo_root`
- `--port`
- `--host`

## Modes

- `mock`: writes into `tools/omega_mission_control/runtime/mock_runs/<runId>/daemon/rsi_omega_daemon_v18_0/{config,state}` and streams from there.
- `fs`: reads existing real run directories under `OMEGA_MC_RUNS_ROOT`.

Mock generator behavior is deterministic by seed (`seed_u64` default `18000001`) and produces:

- `omega_state_v1`
- `omega_observation_report_v1`
- `omega_issue_bundle_v1`
- `omega_decision_plan_v1`
- optional dispatch/subverifier/promotion/activation/rollback receipts
- `omega_trace_hash_chain_v1`
- `omega_tick_snapshot_v1`
- ledger append in coordinator order

## REST API

Exact endpoints:

- `GET /api/v1/runs`
- `GET /api/v1/runs/{runId}/snapshot`
- `GET /api/v1/runs/{runId}/file?rel=<relpath>`

Additional helper endpoints used by UI modules:

- `GET /api/v1/runs/{runId}/dispatches`
- `GET /api/v1/runs/{runId}/dispatch/{dispatchId}/promotion-bundle`
- `GET /api/v1/runs/{runId}/dispatch/{dispatchId}/proofs`
- `GET /api/v1/runs/{runId}/hash-search?hash=sha256:<hex>`
- `GET /api/v1/runs/{runId}/compare-ticks?a=<tick>&b=<tick>`
- `GET /api/v1/runs/{runId}/repo-file?rel=<repo_rel_path>`
- `POST /api/v1/directives`
- `POST /api/v1/uploads`
- `GET /api/v1/uploads`

## WebSocket

`ws://<host>:<port>/ws`

Protocol version: `omega_mc_ws_v1`

Client -> Server:

- `HELLO`
- `SET_PAUSE`
- `REQUEST_ARTIFACT`

Server -> Client:

- `WELCOME`
- `FULL_SNAPSHOT`
- `LEDGER_EVENT`
- `ARTIFACT`
- `DIRECTIVE_SUBMITTED`
- `ERROR`

## Security

Fail-closed path model:

- `run_id` must match `^[A-Za-z0-9._-]{1,128}$`
- reject `..`, absolute paths, null bytes, and backslashes in relative paths
- all resolved paths confined under configured roots

`/api/v1/runs/{runId}/file` enforces text-only and max file size of 2MB.

## Tests

```bash
npm test
```

Includes server security, mock artifact generation, and snapshot resolver coverage.

