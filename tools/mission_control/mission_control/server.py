"""FastAPI server for Mission Control v18.0.

Local web dashboard for visualizing Omega v4.0 and SAS-VAL v17.0 telemetry.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .omega_v4_0 import build_omega_snapshot, get_ledger_events_paginated
from .run_scan import (
    OMEGA_V4_0,
    SAS_VAL_V17_0,
    detect_omega_v4_0,
    detect_sas_val_v17_0,
    scan_runs_root,
)
from .sas_val_v17_0 import build_sas_val_snapshot
from .security import safe_resolve_path, validate_run_id

# Global state (set via CLI args)
_REPO_ROOT: Optional[Path] = None
_RUNS_ROOT: Optional[Path] = None

app = FastAPI(
    title="Mission Control v18.0",
    description="Telemetry visualization for Omega v4.0 and SAS-VAL v17.0 runs",
    version="18.0.0",
)


def get_runs_root() -> Path:
    """Get configured runs root, raising if not set."""
    if _RUNS_ROOT is None:
        raise HTTPException(status_code=500, detail="SERVER_NOT_CONFIGURED")
    return _RUNS_ROOT


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------


@app.get("/api/v1/runs")
def list_runs() -> dict[str, Any]:
    """List all runs with type detection and health status."""
    runs_root = get_runs_root()
    runs = scan_runs_root(runs_root)
    return {
        "runs_root": str(runs_root.resolve()),
        "runs": runs,
    }


@app.get("/api/v1/runs/{run_id}/snapshot")
def get_run_snapshot(run_id: str) -> dict[str, Any]:
    """Get aggregated snapshot for dashboard panels."""
    runs_root = get_runs_root()
    
    # Validate and resolve run path
    run_path = safe_resolve_path(runs_root, run_id)
    if run_path is None or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    
    # Detect types
    detected_types: list[str] = []
    if detect_omega_v4_0(run_path):
        detected_types.append(OMEGA_V4_0)
    if detect_sas_val_v17_0(run_path):
        detected_types.append(SAS_VAL_V17_0)
    
    if not detected_types:
        raise HTTPException(status_code=404, detail="NO_TELEMETRY_DETECTED")
    
    result: dict[str, Any] = {
        "run_id": run_id,
        "detected_types": detected_types,
    }
    
    # Build snapshots for each detected type
    if OMEGA_V4_0 in detected_types:
        result["omega"] = build_omega_snapshot(run_path)
    
    if SAS_VAL_V17_0 in detected_types:
        sas_val = build_sas_val_snapshot(run_path)
        if sas_val:
            result["sas_val"] = sas_val
    
    return result


@app.get("/api/v1/runs/{run_id}/omega/events")
def get_omega_events(
    run_id: str,
    offset: int = Query(default=0, ge=0, description="0-based line index"),
    limit: int = Query(default=200, ge=1, le=500, description="Max events to return"),
) -> dict[str, Any]:
    """Get paginated slice of Omega ledger events."""
    runs_root = get_runs_root()
    
    # Validate and resolve run path
    run_path = safe_resolve_path(runs_root, run_id)
    if run_path is None or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    
    if not detect_omega_v4_0(run_path):
        raise HTTPException(status_code=404, detail="NOT_OMEGA_RUN")
    
    ledger_path = run_path / "omega" / "omega_ledger_v1.jsonl"
    events = get_ledger_events_paginated(ledger_path, offset=offset, limit=limit)
    
    return {
        "run_id": run_id,
        "offset": offset,
        "limit": limit,
        "count": len(events),
        "events": events,
    }


# -----------------------------------------------------------------------------
# Static Files
# -----------------------------------------------------------------------------

# Get the static directory path
_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def serve_index() -> FileResponse:
    """Serve the main index.html page."""
    return FileResponse(_STATIC_DIR / "index.html")


# Mount static files for CSS/JS
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for starting the server."""
    parser = argparse.ArgumentParser(
        prog="python -m mission_control.server",
        description="Mission Control v18.0 - Telemetry Visualization UI",
    )
    parser.add_argument(
        "--repo_root",
        required=True,
        type=Path,
        help="Path to the repository root",
    )
    parser.add_argument(
        "--runs_root",
        required=True,
        type=Path,
        help="Path to the runs directory",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="Port to bind to (default: 8787)",
    )
    
    args = parser.parse_args()
    
    # Validate paths
    if not args.repo_root.is_dir():
        parser.error(f"repo_root does not exist: {args.repo_root}")
    if not args.runs_root.is_dir():
        parser.error(f"runs_root does not exist: {args.runs_root}")
    
    # Set global state
    global _REPO_ROOT, _RUNS_ROOT
    _REPO_ROOT = args.repo_root.resolve()
    _RUNS_ROOT = args.runs_root.resolve()
    
    # Start server
    import uvicorn
    
    print(f"Mission Control v18.0")
    print(f"  repo_root: {_REPO_ROOT}")
    print(f"  runs_root: {_RUNS_ROOT}")
    print(f"  URL: http://{args.host}:{args.port}/")
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
