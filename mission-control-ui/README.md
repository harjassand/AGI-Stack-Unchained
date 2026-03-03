# Mission Control UI

Next.js App Router frontend for live Mission Control observability and operator interaction.

## Scope

- Render live mission telemetry and execution state.
- Stream daemon events from server SSE endpoints.
- Provide mission-ingest and command interaction surfaces.

## Runtime Contract

The UI integrates with the Mission Control server using:

- `GET /stream` for server-sent event streaming.
- `GET /api/state/current` for periodic state snapshots.
- `POST /api/mission` for mission ingest actions.

## Local Development

```bash
cd mission-control-ui
npm install
npm run dev
```

Default dev bind: `127.0.0.1:3000`.

## Environment Variables

- `NEXT_PUBLIC_MC_SERVER_BASE`: Base URL for the backend API/SSE server.

Example local override:

```bash
echo 'NEXT_PUBLIC_MC_SERVER_BASE=http://127.0.0.1:7890' > .env.local
```

## Production Build

```bash
npm run build
npm run start
```

## Quality Checks

```bash
npm run lint
```

## UI Composition

- Left panel: command console, goal queue, host health.
- Center panel: live SSE monologue and signal DAG visualization (`reactflow`).
- Right panel: high-priority artifact feed (for example `ACTIVATION_COMMIT`, `CCAP_DECISION`) and bundle status.

## Reliability Notes

- SSE client uses native `EventSource` and reconnects after disconnect.
- Stream events are deduplicated by sequence ID when present.
