from __future__ import annotations

import json
from pathlib import Path

from orchestrator.omega_v18_0 import coordinator_v1 as coordinator


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_load_prev_observation_prefers_highest_tick_over_filename_order(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "runs" / "series_a" / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    obs_dir = state_root / "observations"

    # Lexicographically later filename intentionally has an older tick.
    _write_json(
        obs_dir / ("sha256_" + ("f" * 64) + ".omega_observation_report_v1.json"),
        {
            "schema_version": "omega_observation_report_v1",
            "tick_u64": 1,
            "metric_series": {},
        },
    )
    _write_json(
        obs_dir / ("sha256_" + ("0" * 64) + ".omega_observation_report_v1.json"),
        {
            "schema_version": "omega_observation_report_v1",
            "tick_u64": 2,
            "metric_series": {},
        },
    )

    monkeypatch.setattr(coordinator, "validate_schema", lambda *_args, **_kwargs: None)
    payload, source = coordinator._load_prev_observation(state_root)

    assert isinstance(payload, dict)
    assert int(payload.get("tick_u64", -1)) == 2
    assert isinstance(source, dict)
    assert source.get("producer_run_id") == "series_a"
