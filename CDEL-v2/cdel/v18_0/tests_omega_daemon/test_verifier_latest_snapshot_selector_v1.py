from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier


def test_latest_snapshot_selector_picks_highest_tick(tmp_path: Path) -> None:
    snapshots = tmp_path / "snapshot"
    snapshots.mkdir(parents=True, exist_ok=True)
    older = snapshots / "sha256_1111111111111111111111111111111111111111111111111111111111111111.omega_tick_snapshot_v1.json"
    newer = snapshots / "sha256_ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff.omega_tick_snapshot_v1.json"
    older.write_text('{"tick_u64":3}\n', encoding="utf-8")
    newer.write_text('{"tick_u64":2}\n', encoding="utf-8")

    selected = verifier._latest_snapshot_or_fail(snapshots)
    assert selected == older
