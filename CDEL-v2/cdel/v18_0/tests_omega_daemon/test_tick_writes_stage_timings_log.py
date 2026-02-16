from __future__ import annotations

from .utils import run_tick_once


def test_tick_writes_stage_timings_log(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    timings_path = state_dir / "ledger" / "timings.log"
    assert timings_path.exists()

    lines = [line.strip() for line in timings_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    line = lines[0]
    assert "tick_u64=1" in line
    for stage in (
        "freeze_pack_config",
        "observe",
        "diagnose",
        "decide",
        "dispatch_campaign",
        "run_subverifier",
        "run_promotion",
        "run_activation",
        "ledger_writes",
        "trace_write",
        "snapshot_write",
    ):
        assert f"{stage}_ns=" in line
    assert "total_ns=" in line
