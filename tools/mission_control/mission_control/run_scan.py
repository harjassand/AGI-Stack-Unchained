"""Run directory scanner for Mission Control.

Detects run types (OMEGA_V4_0, SAS_VAL_V17_0) and health status.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Run type constants
OMEGA_V4_0 = "OMEGA_V4_0"
SAS_VAL_V17_0 = "SAS_VAL_V17_0"

# Health status constants
HEALTH_OK = "OK"
HEALTH_MISSING_ARTIFACT = "MISSING_ARTIFACT"


def _get_mtime_utc(path: Path) -> Optional[datetime]:
    """Get file modification time as UTC datetime."""
    try:
        stat = path.stat()
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except (OSError, ValueError):
        return None


def _max_mtime_recursive(path: Path, extensions: tuple[str, ...] = ()) -> Optional[datetime]:
    """Get max mtime of files under a path, optionally filtered by extension."""
    max_mtime: Optional[datetime] = None
    try:
        for root, _, files in os.walk(path):
            root_path = Path(root)
            for fname in files:
                if extensions and not fname.endswith(extensions):
                    continue
                file_path = root_path / fname
                mtime = _get_mtime_utc(file_path)
                if mtime and (max_mtime is None or mtime > max_mtime):
                    max_mtime = mtime
    except (OSError, ValueError):
        pass
    return max_mtime


def detect_omega_v4_0(run_path: Path) -> bool:
    """Detect if run directory contains Omega v4.0 artifacts.
    
    Omega v4.0 is identified by presence of:
    - omega/omega_ledger_v1.jsonl
    - omega/checkpoints/ directory
    """
    omega_dir = run_path / "omega"
    if not omega_dir.is_dir():
        return False
    ledger = omega_dir / "omega_ledger_v1.jsonl"
    checkpoints = omega_dir / "checkpoints"
    return ledger.is_file() and checkpoints.is_dir()


def _resolve_sas_val_state(path: Path) -> Optional[Path]:
    """Resolve SAS-VAL v17.0 state directory using 3-case logic.
    
    Same resolution logic as verify_rsi_sas_val_v1._resolve_state:
    1. root/daemon/rsi_sas_val_v17_0/state
    2. root/state when root/config exists
    3. path itself when it contains 'inputs' and parent has 'config'
    
    Returns state_dir if found, None otherwise.
    """
    root = path.resolve()
    
    # Case 1: daemon structure
    candidate = root / "daemon" / "rsi_sas_val_v17_0" / "state"
    if candidate.exists():
        return candidate
    
    # Case 2: root/state with root/config
    candidate = root / "state"
    if candidate.exists() and (root / "config").exists():
        return candidate
    
    # Case 3: path is state dir itself
    if (root / "inputs").exists() and (root.parent / "config").exists():
        return root
    
    return None


def detect_sas_val_v17_0(run_path: Path) -> bool:
    """Detect if run directory contains SAS-VAL v17.0 artifacts."""
    state_dir = _resolve_sas_val_state(run_path)
    return state_dir is not None


def check_omega_health(run_path: Path) -> str:
    """Check health of Omega v4.0 run artifacts."""
    omega_dir = run_path / "omega"
    ledger = omega_dir / "omega_ledger_v1.jsonl"
    checkpoints = omega_dir / "checkpoints"
    
    if not ledger.is_file():
        return HEALTH_MISSING_ARTIFACT
    if not checkpoints.is_dir():
        return HEALTH_MISSING_ARTIFACT
    
    # Check for at least one checkpoint receipt
    checkpoint_files = list(checkpoints.glob("sha256_*.omega_checkpoint_receipt_v1.json"))
    if not checkpoint_files:
        return HEALTH_MISSING_ARTIFACT
    
    return HEALTH_OK


def check_sas_val_health(run_path: Path) -> str:
    """Check health of SAS-VAL v17.0 run artifacts."""
    state_dir = _resolve_sas_val_state(run_path)
    if state_dir is None:
        return HEALTH_MISSING_ARTIFACT
    
    # Check for promotion bundle
    promo_dir = state_dir / "promotion"
    if not promo_dir.is_dir():
        return HEALTH_MISSING_ARTIFACT
    
    promo_files = list(promo_dir.glob("sha256_*.sas_val_promotion_bundle_v1.json"))
    if not promo_files:
        return HEALTH_MISSING_ARTIFACT
    
    return HEALTH_OK


def get_run_last_seen(run_path: Path, detected_types: list[str]) -> Optional[str]:
    """Get last_seen_utc as ISO string from max mtime of relevant files."""
    max_mtime: Optional[datetime] = None
    
    if OMEGA_V4_0 in detected_types:
        omega_dir = run_path / "omega"
        if omega_dir.is_dir():
            mtime = _max_mtime_recursive(omega_dir, (".jsonl", ".json"))
            if mtime and (max_mtime is None or mtime > max_mtime):
                max_mtime = mtime
    
    if SAS_VAL_V17_0 in detected_types:
        state_dir = _resolve_sas_val_state(run_path)
        if state_dir:
            mtime = _max_mtime_recursive(state_dir, (".json", ".jsonl"))
            if mtime and (max_mtime is None or mtime > max_mtime):
                max_mtime = mtime
    
    if max_mtime:
        return max_mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def scan_run(run_path: Path) -> Optional[dict[str, Any]]:
    """Scan a single run directory for type and health.
    
    Returns dict with run_id, abs_path, detected_types, last_seen_utc, health.
    Returns None if directory doesn't exist or has no detectable types.
    """
    if not run_path.is_dir():
        return None
    
    run_id = run_path.name
    detected_types: list[str] = []
    
    if detect_omega_v4_0(run_path):
        detected_types.append(OMEGA_V4_0)
    
    if detect_sas_val_v17_0(run_path):
        detected_types.append(SAS_VAL_V17_0)
    
    if not detected_types:
        return None
    
    # Determine health (OK only if all detected types are healthy)
    health = HEALTH_OK
    if OMEGA_V4_0 in detected_types:
        if check_omega_health(run_path) != HEALTH_OK:
            health = HEALTH_MISSING_ARTIFACT
    if SAS_VAL_V17_0 in detected_types:
        if check_sas_val_health(run_path) != HEALTH_OK:
            health = HEALTH_MISSING_ARTIFACT
    
    last_seen = get_run_last_seen(run_path, detected_types)
    
    return {
        "run_id": run_id,
        "abs_path": str(run_path.resolve()),
        "detected_types": detected_types,
        "last_seen_utc": last_seen,
        "health": health,
    }


def scan_runs_root(runs_root: Path) -> list[dict[str, Any]]:
    """Scan all subdirectories under runs_root for detectable runs.
    
    Returns list of run info dicts, sorted by run_id.
    """
    runs: list[dict[str, Any]] = []
    
    if not runs_root.is_dir():
        return runs
    
    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir():
            continue
        # Skip hidden directories and special directories
        if entry.name.startswith("."):
            continue
        
        run_info = scan_run(entry)
        if run_info:
            runs.append(run_info)
    
    return runs


def resolve_sas_val_state(run_path: Path) -> Optional[Path]:
    """Public interface to resolve SAS-VAL state directory."""
    return _resolve_sas_val_state(run_path)


__all__ = [
    "OMEGA_V4_0",
    "SAS_VAL_V17_0",
    "HEALTH_OK",
    "HEALTH_MISSING_ARTIFACT",
    "detect_omega_v4_0",
    "detect_sas_val_v17_0",
    "check_omega_health",
    "check_sas_val_health",
    "scan_run",
    "scan_runs_root",
    "resolve_sas_val_state",
]
