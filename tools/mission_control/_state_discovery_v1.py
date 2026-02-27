from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from tools.mission_control.mission_pipeline_v1 import current_mission_summary, recent_mission_events

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_BUNDLE_RELPATH = "meta-core/active/ACTIVE_BUNDLE"
STATE_GLOB = "daemon/*/state/omega_state_v1.json"
_STATE_DISCOVERY_CACHE_TTL_S = 2.0
_STATE_DISCOVERY_CACHE: Dict[str, Any] = {"ts": 0.0, "path": None, "source": ""}
_RUNS_SCAN_MAX_DEPTH = 8
_RUNS_SCAN_PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
}


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return -1.0


def _scan_runs_for_latest_state(runs_root: Path) -> Optional[Path]:
    best_path: Optional[Path] = None
    best_mtime = -1.0

    for root, dirs, files in os.walk(runs_root, topdown=True, followlinks=False):
        try:
            rel_depth = len(Path(root).relative_to(runs_root).parts)
        except ValueError:
            rel_depth = 0

        kept_dirs = []
        for dirname in dirs:
            full = Path(root) / dirname
            if full.is_symlink():
                continue
            if dirname in _RUNS_SCAN_PRUNE_DIRS:
                continue
            kept_dirs.append(dirname)
        if rel_depth >= _RUNS_SCAN_MAX_DEPTH:
            dirs[:] = []
        else:
            dirs[:] = kept_dirs

        if "omega_state_v1.json" not in files:
            continue
        if Path(root).name != "state":
            continue

        candidate = Path(root) / "omega_state_v1.json"
        if not candidate.is_file():
            continue
        candidate_mtime = _safe_mtime(candidate)
        if candidate_mtime >= best_mtime:
            best_mtime = candidate_mtime
            best_path = candidate

    return best_path


def _discover_state_path_info_uncached(repo_root: Path = REPO_ROOT) -> Tuple[Optional[Path], str]:
    mc_state_path = os.getenv("MC_STATE_PATH")
    if mc_state_path:
        candidate = Path(mc_state_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate, "env"

    candidates = [path for path in repo_root.glob(STATE_GLOB) if path.is_file()]
    if candidates:
        return max(candidates, key=_safe_mtime), "daemon_default"

    runs_root = repo_root / "runs"
    if runs_root.exists() and runs_root.is_dir():
        latest = _scan_runs_for_latest_state(runs_root)
        if latest is not None:
            return latest, "runs_scan"

    return None, ""


def discover_state_path_info(repo_root: Path = REPO_ROOT) -> Tuple[Optional[Path], str]:
    now = time.monotonic()
    cached_ts = float(_STATE_DISCOVERY_CACHE.get("ts", 0.0))
    cached_path = _STATE_DISCOVERY_CACHE.get("path")
    cached_source = str(_STATE_DISCOVERY_CACHE.get("source", ""))
    if isinstance(cached_path, Path) and now - cached_ts < _STATE_DISCOVERY_CACHE_TTL_S:
        if cached_path.exists() and cached_path.is_file():
            return cached_path, cached_source
    if cached_path is None and now - cached_ts < _STATE_DISCOVERY_CACHE_TTL_S:
        return None, ""

    selected, source = _discover_state_path_info_uncached(repo_root=repo_root)
    _STATE_DISCOVERY_CACHE["ts"] = now
    _STATE_DISCOVERY_CACHE["path"] = selected
    _STATE_DISCOVERY_CACHE["source"] = source
    return selected, source


def discover_state_path(repo_root: Path = REPO_ROOT) -> Optional[Path]:
    state_path, _source = discover_state_path_info(repo_root=repo_root)
    return state_path


def load_omega_state(repo_root: Path = REPO_ROOT) -> Optional[Any]:
    state_path, _source = discover_state_path_info(repo_root=repo_root)
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
    state_path, state_source = discover_state_path_info(repo_root=repo_root)
    omega_state = None
    if state_path is not None:
        try:
            omega_state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            omega_state = None

    mission_summary = current_mission_summary(repo_root=repo_root)
    mission_id = mission_summary.get("mission_id") if isinstance(mission_summary, dict) else None
    mission_events = recent_mission_events(
        mission_id=mission_id if isinstance(mission_id, str) else None,
        limit=40,
        repo_root=repo_root,
    )

    return {
        "ts_unix_ms": int(time.time() * 1000),
        "omega_state": omega_state,
        "state_meta": {
            "found_b": state_path is not None,
            "selected_path": str(state_path.resolve()) if state_path else "",
            "source": state_source if state_path else "",
        },
        "active_bundle": read_active_bundle(repo_root=repo_root),
        "host": host_metrics(),
        "mission_control": {
            "summary": mission_summary,
            "recent_events": mission_events,
        },
    }
