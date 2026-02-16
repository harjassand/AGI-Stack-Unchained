from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v6_0.verify_rsi_persistence_v1 import verify
from .utils import build_entry, write_ledger, write_pack, write_receipt, write_snapshot


def _setup_state(tmp_path: Path) -> tuple[Path, dict[str, str]]:
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
    return state_dir, {"good_head": entries[-1]["entry_hash"]}


def test_v6_0_checkpoint_binds_head(tmp_path: Path) -> None:
    state_dir, refs = _setup_state(tmp_path)

    # Valid in prefix mode
    verify(state_dir, mode="prefix")

    # Tamper: checkpoint receipt references non-existent head
    bad_receipt_path = next((state_dir / "checkpoints").glob("sha256_*.daemon_checkpoint_receipt_v1.json"))
    receipt = bad_receipt_path.read_text(encoding="utf-8")
    receipt = receipt.replace(refs["good_head"], "0" * 64)
    bad_receipt_path.write_text(receipt, encoding="utf-8")

    with pytest.raises(Exception):
        verify(state_dir, mode="prefix")
