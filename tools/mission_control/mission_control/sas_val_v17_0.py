"""SAS-VAL v17.0 telemetry parser for Mission Control.

Read-only parsing of promotion bundles and hotloop reports.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


def resolve_state(path: Path) -> Optional[tuple[Path, Path]]:
    """Resolve SAS-VAL v17.0 state directory using 3-case logic.
    
    Same resolution logic as verify_rsi_sas_val_v1._resolve_state:
    1. root/daemon/rsi_sas_val_v17_0/state → (state, state.parent)
    2. root/state when root/config exists → (state, root)
    3. path itself when it contains 'inputs' and parent has 'config' → (path, path.parent)
    
    Returns (state_dir, daemon_root) if found, None otherwise.
    """
    root = path.resolve()
    
    # Case 1: daemon structure
    candidate = root / "daemon" / "rsi_sas_val_v17_0" / "state"
    if candidate.exists():
        return candidate, candidate.parent
    
    # Case 2: root/state with root/config
    candidate = root / "state"
    if candidate.exists() and (root / "config").exists():
        return candidate, root
    
    # Case 3: path is state dir itself
    if (root / "inputs").exists() and (root.parent / "config").exists():
        return root, root.parent
    
    return None


def load_json_safe(path: Path) -> Optional[dict[str, Any]]:
    """Load JSON file safely, returning None on any error."""
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def find_latest_promotion_bundle(state_dir: Path) -> Optional[dict[str, Any]]:
    """Find and load the latest promotion bundle by lexicographic filename.
    
    Files: state_dir/promotion/sha256_*.sas_val_promotion_bundle_v1.json
    """
    promo_dir = state_dir / "promotion"
    if not promo_dir.is_dir():
        return None
    
    bundle_files = sorted(promo_dir.glob("sha256_*.sas_val_promotion_bundle_v1.json"))
    if not bundle_files:
        return None
    
    # Latest by lexicographic max filename
    latest = bundle_files[-1]
    return load_json_safe(latest)


def extract_hash_from_ref(hash_ref: str) -> Optional[str]:
    """Extract hex hash from sha256:xxx format."""
    if not isinstance(hash_ref, str):
        return None
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", hash_ref):
        return None
    return hash_ref.split(":", 1)[1]


def find_hotloop_by_hash(state_dir: Path, hotloop_hash: str) -> Optional[dict[str, Any]]:
    """Find hotloop report by hash reference.
    
    File: state_dir/hotloop/sha256_<hex>.kernel_hotloop_report_v1.json
    """
    hex_hash = extract_hash_from_ref(hotloop_hash)
    if not hex_hash:
        return None
    
    hotloop_dir = state_dir / "hotloop"
    target = hotloop_dir / f"sha256_{hex_hash}.kernel_hotloop_report_v1.json"
    return load_json_safe(target)


def extract_gate_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract gate booleans and cycle counts from promotion bundle."""
    return {
        "bundle_id": bundle.get("bundle_id"),
        "val_cycles_baseline": bundle.get("val_cycles_baseline"),
        "val_cycles_candidate": bundle.get("val_cycles_candidate"),
        "valcycles_gate_pass": bundle.get("valcycles_gate_pass"),
        "wallclock_gate_pass": bundle.get("wallclock_gate_pass"),
        "work_conservation_pass": bundle.get("work_conservation_pass"),
    }


def extract_hotloop_summary(hotloop: dict[str, Any]) -> dict[str, Any]:
    """Extract hotloop summary with top_loops table."""
    top_loops = hotloop.get("top_loops", [])
    
    # Normalize top_loops to include required fields
    normalized_loops = []
    for loop in top_loops:
        if not isinstance(loop, dict):
            continue
        normalized_loops.append({
            "loop_id": loop.get("loop_id"),
            "iters": loop.get("iters"),
            "bytes": loop.get("bytes"),
            "ops_add": loop.get("ops_add"),
            "ops_mul": loop.get("ops_mul"),
            "ops_load": loop.get("ops_load"),
            "ops_store": loop.get("ops_store"),
        })
    
    return {
        "pilot_loop_id": hotloop.get("pilot_loop_id"),
        "dominant_loop_id": hotloop.get("dominant_loop_id"),
        "top_n": hotloop.get("top_n"),
        "source_symbol": hotloop.get("source_symbol"),
        "top_loops": normalized_loops,
    }


def build_sas_val_snapshot(run_path: Path) -> Optional[dict[str, Any]]:
    """Build complete SAS-VAL v17.0 snapshot for dashboard.
    
    Args:
        run_path: Path to run directory.
        
    Returns:
        Dict with all fields needed for SAS-VAL dashboard panels,
        or None if SAS-VAL artifacts not found.
    """
    result = resolve_state(run_path)
    if result is None:
        return None
    
    state_dir, _ = result
    
    # Load promotion bundle
    bundle = find_latest_promotion_bundle(state_dir)
    if bundle is None:
        return None
    
    # Extract gates summary
    gates = extract_gate_summary(bundle)
    
    # Load hotloop report referenced by bundle
    hotloop_hash = bundle.get("hotloop_report_hash")
    hotloop = None
    hotloop_summary = None
    if hotloop_hash:
        hotloop = find_hotloop_by_hash(state_dir, hotloop_hash)
        if hotloop:
            hotloop_summary = extract_hotloop_summary(hotloop)
    
    return {
        "val_gates": gates,
        "hotloops": hotloop_summary,
    }


__all__ = [
    "resolve_state",
    "find_latest_promotion_bundle",
    "find_hotloop_by_hash",
    "extract_gate_summary",
    "extract_hotloop_summary",
    "build_sas_val_snapshot",
]
