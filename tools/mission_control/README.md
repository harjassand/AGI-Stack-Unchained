# Mission Control v18.0

Local web dashboard for visualizing Omega v4.0 and SAS-VAL v17.0 telemetry.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the dashboard
python3 -m mission_control.server --repo_root . --runs_root ./runs --host 127.0.0.1 --port 8787
```

Then open http://127.0.0.1:8787/ in your browser.

## Features

### Run Chooser (Landing Page)
- Lists all runs with detected types (Omega v4.0, SAS-VAL v17.0)
- Shows health status and last activity timestamp
- Click a row to view run details

### Omega v4.0 Dashboard
- **Current Focus**: Real-time focus state derived from last event type
- **Performance Metrics**: Task pass rates, compute usage, acceleration metrics
- **Verified Discoveries**: Table of successful promotions
- **Proposals**: Emitted and evaluated proposals with decisions
- **Event Stream**: Last 200 events with 1Hz auto-refresh
- **Ignition Status**: Latest ignition proof if present

### SAS-VAL v17.0 Dashboard
- **VAL Gates**: Gate pass/fail status from promotion bundle
- **Hotloops**: Top loops with performance metrics (iters, bytes, ops)

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/runs` | List all runs with type detection |
| `GET /api/v1/runs/{run_id}/snapshot` | Complete snapshot for dashboard |
| `GET /api/v1/runs/{run_id}/omega/events` | Paginated ledger events |

## Security

- **Run ID Validation**: Regex `^[A-Za-z0-9._-]{1,128}$`
- **Path Traversal Protection**: Rejects `..`, absolute paths, null bytes
- **Root Confinement**: All paths must resolve within runs_root
- **Read-Only**: No writes to run directories

## Architecture

```
tools/mission_control/
├── mission_control/
│   ├── __init__.py       # Package marker
│   ├── __main__.py       # Module entry point
│   ├── server.py         # FastAPI server
│   ├── security.py       # Path validation
│   ├── run_scan.py       # Run detection
│   ├── omega_v4_0.py     # Omega parser
│   ├── sas_val_v17_0.py  # SAS-VAL parser
│   └── static/
│       ├── index.html    # SPA structure
│       ├── styles.css    # Dark theme
│       └── app.js        # Frontend logic
├── tests/
│   ├── conftest.py
│   ├── test_security.py
│   ├── test_run_scan.py
│   ├── test_omega_snapshot.py
│   └── test_sas_val_snapshot.py
├── requirements.txt
└── README.md
```

## Running Tests

```bash
pytest tools/mission_control/tests -q
```

## License

Internal use only.
