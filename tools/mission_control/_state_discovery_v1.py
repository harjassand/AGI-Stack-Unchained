from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_BUNDLE_RELPATH = "meta-core/active/ACTIVE_BUNDLE"
STATE_GLOB = "daemon/*/state/omega_state_v1.json"


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return -1.0


def discover_state_path(repo_root: Path = REPO_ROOT) -> Optional[Path]:
    mc_state_path = os.getenv("MC_STATE_PATH")
    if mc_state_path:
        candidate = Path(mc_state_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate

    candidates = [path for path in repo_root.glob(STATE_GLOB) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=_safe_mtime)


def load_omega_state(repo_root: Path = REPO_ROOT) -> Optional[Any]:
    state_path = discover_state_path(repo_root=repo_root)
    if state_path is None:
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_active_bundle(repo_root: Path = REPO_ROOT) -> Dict[str, str]:
    active_bundle_path = repo_root / ACTIVE_BUNDLE_RELPATH
    active_bundle_value = ""
    if active_bundle_path.exists() and active_bundle_path.is_file():
        try:
            active_bundle_value = active_bundle_path.read_text(encoding="utf-8").strip()
        except OSError:
            active_bundle_value = ""
    return {
        "active_bundle_relpath": ACTIVE_BUNDLE_RELPATH,
        "active_bundle_value": active_bundle_value,
    }


def host_metrics() -> Dict[str, float]:
    try:
        import psutil  # type: ignore
    except ImportError:
        return {"rss_bytes": 0, "vms_bytes": 0, "cpu_pct": 0.0}

    try:
        process = psutil.Process(os.getpid())
        memory = process.memory_info()
        return {
            "rss_bytes": int(getattr(memory, "rss", 0)),
            "vms_bytes": int(getattr(memory, "vms", 0)),
            "cpu_pct": float(psutil.cpu_percent(interval=None)),
        }
    except Exception:
        return {"rss_bytes": 0, "vms_bytes": 0, "cpu_pct": 0.0}


def build_current_state_payload(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    return {
        "ts_unix_ms": int(time.time() * 1000),
        "omega_state": load_omega_state(repo_root=repo_root),
        "active_bundle": read_active_bundle(repo_root=repo_root),
        "host": host_metrics(),
    }
