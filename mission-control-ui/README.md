# Mission Control UI (Phase 3)

Next.js App Router dashboard for the Mission Control contract:

- SSE stream: `GET /stream`
- State polling: `GET /api/state/current` (1 Hz)
- Mission ingest: `POST /api/mission`

## Local Run

```bash
cd mission-control-ui
npm install
npm run dev
```

The dev server binds to `127.0.0.1:3000`.

## FastAPI Base URL

The UI reads:

- `NEXT_PUBLIC_MC_SERVER_BASE`

Default:

- `http://127.0.0.1:7890`

Optional local override:

```bash
echo 'NEXT_PUBLIC_MC_SERVER_BASE=http://127.0.0.1:7890' > .env.local
```

## Dashboard Panels

- Left: command console, goal queue, and host health.
- Center: live SSE monologue and signal DAG (`reactflow`).
- Right: latest important artifact (`ACTIVATION_COMMIT` / `CCAP_DECISION`) and active bundle value.

## Notes

- SSE client uses native `EventSource` and reconnects 1 second after disconnect.
- Events are deduplicated by `seq` when present.
