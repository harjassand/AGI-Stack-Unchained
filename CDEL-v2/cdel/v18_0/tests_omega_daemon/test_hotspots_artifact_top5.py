from __future__ import annotations

from cdel.v18_0.omega_hotspots_v1 import build_hotspots


def test_hotspots_artifact_top5_ordered() -> None:
    payload = build_hotspots(
        tick_u64=10,
        total_ns_u64=1000,
        stage_ns={
            "observe": 100,
            "diagnose": 50,
            "decide": 150,
            "dispatch_campaign": 300,
            "run_subverifier": 250,
            "run_promotion": 50,
            "run_activation": 10,
            "freeze_pack_config": 5,
            "ledger_writes": 5,
            "trace_write": 5,
            "snapshot_write": 5,
        },
    )
    rows = payload["top_hotspots"]
    assert len(rows) == 5
    assert rows[0]["stage_id"] == "dispatch"
    assert any(str(row["stage_id"]) == "subverify" for row in rows)
