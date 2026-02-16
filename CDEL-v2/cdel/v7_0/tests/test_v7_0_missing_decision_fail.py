from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v7_0.verify_rsi_run_with_superego_v1 import verify
from .utils import (
    build_entry,
    build_request,
    write_alignment_artifacts,
    write_alignment_pack,
    write_daemon_pack,
    write_ledger,
    write_receipt,
    write_snapshot,
)


def test_v7_0_missing_decision_fail(tmp_path: Path) -> None:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v7_0"
    state_dir = daemon_root / "state"
    config_dir = daemon_root / "config"
    alignment_dir = state_dir / "alignment"
    (state_dir / "ledger").mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    (state_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (state_dir / "boots").mkdir(parents=True, exist_ok=True)
    (state_dir / "control").mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    sealed_config = tmp_path / "sealed_alignment_fixture_v1.toml"
    sealed_config.write_text("suite_id = 'fixture'\n", encoding="utf-8")
    write_alignment_pack(
        config_dir,
        sealed_path=str(sealed_config),
        thresholds={"min_align_score_num": 1, "min_align_score_den": 2, "hard_fail_max": 0},
    )
    pack = write_daemon_pack(config_dir, state_dir=state_dir, alignment_pack_path=str(sealed_config))
    write_alignment_artifacts(alignment_dir, clearance_level="BOUNDLESS")

    req = build_request(
        {
            "daemon_id": "sha256:" + "0" * 64,
            "tick": 1,
            "objective_class": "MAINTENANCE",
            "objective_text": "noop",
            "capabilities": ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "NETWORK_NONE"],
            "target_paths": [str(state_dir)],
            "sealed_eval_required": False,
        }
    )

    prev = "GENESIS"
    entries = [
        build_entry(1, 0, "BOOT", prev),
    ]
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(2, 1, "TICK_BEGIN", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(3, 1, "SUPEREGO_REQUEST", prev, {"request_id": req["request_id"], "objective_class": "MAINTENANCE"}))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(4, 1, "ACTION_EXECUTED", prev, {"request_id": req["request_id"], "objective_class": "MAINTENANCE"}))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(5, 1, "CHECKPOINT", prev))

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
        "daemon_id": snapshot["daemon_id"],
        "icore_id": snapshot["icore_id"],
        "meta_hash": snapshot["meta_hash"],
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
        "daemon_id": snapshot["daemon_id"],
        "icore_id": snapshot["icore_id"],
        "meta_hash": snapshot["meta_hash"],
        "tick": 1,
        "boot_count": 1,
        "ledger_head_hash": entries[-1]["entry_hash"],
        "snapshot_hash": snap_hash,
        "created_utc": "2026-02-04T00:00:01Z",
    }
    write_receipt(state_dir / "checkpoints", checkpoint_receipt)

    with pytest.raises(Exception):
        verify(state_dir, mode="prefix")
