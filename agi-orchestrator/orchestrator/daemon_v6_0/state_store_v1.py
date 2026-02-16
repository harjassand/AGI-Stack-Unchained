"""Snapshot load/save helpers for daemon v6.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v6_0.daemon_state import compute_snapshot_hash, load_snapshot

from .io_atomic_v1 import atomic_write_json


def load_latest_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not snapshot_dir.exists():
        return None, None
    best: dict[str, Any] | None = None
    best_hash: str | None = None
    best_tick = -1
    best_boot = -1
    for path in snapshot_dir.glob("sha256_*.daemon_state_snapshot_v1.json"):
        snapshot = load_snapshot(path)
        tick = int(snapshot.get("tick", 0))
        boot = int(snapshot.get("boot_count", 0))
        if tick > best_tick or (tick == best_tick and boot > best_boot):
            best = snapshot
            best_hash = compute_snapshot_hash(snapshot)
            best_tick = tick
            best_boot = boot
    return best, best_hash


def write_snapshot(snapshot_dir: Path, snapshot: dict[str, Any]) -> tuple[str, Path]:
    snap_hash = compute_snapshot_hash(snapshot)
    name = f"sha256_{snap_hash.split(':', 1)[1]}.daemon_state_snapshot_v1.json"
    path = snapshot_dir / name
    atomic_write_json(path, snapshot)
    return snap_hash, path


__all__ = ["load_latest_snapshot", "write_snapshot"]
