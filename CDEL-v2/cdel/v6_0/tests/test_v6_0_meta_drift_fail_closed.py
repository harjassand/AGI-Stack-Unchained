from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v6_0.daemon_state import compute_daemon_id
from cdel.v6_0.verify_rsi_persistence_v1 import verify
from .utils import build_entry, write_ledger, write_pack, write_receipt, write_snapshot


def test_v6_0_meta_drift_fail_closed(tmp_path: Path) -> None:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v6_0"
    state_dir = daemon_root / "state"
    config_dir = daemon_root / "config"
    (state_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    (state_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (state_dir / "boots").mkdir(parents=True, exist_ok=True)
    (state_dir / "control").mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    pack = write_pack(config_dir, state_dir=state_dir)

    # Introduce meta drift while keeping pack self-consistent.
    pack["meta_hash"] = "0" * 64
    pack["daemon_id"] = compute_daemon_id(pack)
    from cdel.v1_7r.canon import write_canon_json

    write_canon_json(config_dir / "rsi_daemon_pack_v1.json", pack)

    prev = "GENESIS"
    entries = []
    entries.append(build_entry(1, 0, "BOOT", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(2, 1, "TICK_BEGIN", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(3, 1, "ACTIVITY_DONE", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(4, 1, "CHECKPOINT", prev))
    write_ledger(state_dir / "ledger" / "daemon_ledger_v1.jsonl", entries)

    snapshot = {
        "schema_version": "daemon_state_snapshot_v1",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 1,
        "ledger_head_hash": entries[-1]["entry_hash"],
        "last_checkpoint_hash": None,
        "boot_count": 1,
        "paused_reason": None,
        "budget_counters": {"ticks_today": 1},
    }
    snap_hash = write_snapshot(state_dir / "snapshots", snapshot)

    boot_receipt = {
        "schema_version": "daemon_boot_receipt_v1",
        "kind": "BOOT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 0,
        "boot_count": 1,
        "ledger_head_hash": entries[0]["entry_hash"],
        "euid": 501,
        "created_utc": "2026-02-04T00:00:00Z",
    }
    write_receipt(state_dir / "boots", boot_receipt)

    checkpoint_receipt = {
        "schema_version": "daemon_checkpoint_receipt_v1",
        "kind": "CHECKPOINT",
        "daemon_id": pack["daemon_id"],
        "icore_id": pack["icore_id"],
        "meta_hash": pack["meta_hash"],
        "tick": 1,
        "boot_count": 1,
        "ledger_head_hash": entries[-1]["entry_hash"],
        "snapshot_hash": snap_hash,
        "created_utc": "2026-02-04T00:00:01Z",
    }
    write_receipt(state_dir / "checkpoints", checkpoint_receipt)

    with pytest.raises(Exception):
        verify(state_dir, mode="prefix")
