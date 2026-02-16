from __future__ import annotations

import json
from pathlib import Path


_PACKS = [
    "rsi_omega_daemon_v18_0",
    "rsi_omega_daemon_v18_0_prod",
    "rsi_omega_daemon_v19_0",
    "rsi_omega_daemon_v19_0_llm_enabled",
    "rsi_omega_daemon_v19_0_unified",
    "rsi_omega_daemon_v19_0_super_unified",
]
_OBJECTIVE_IDS = {
    "OBJ_EXPAND_CAPABILITIES",
    "OBJ_MAXIMIZE_SCIENCE",
    "OBJ_MAXIMIZE_SPEED",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_daemon_pack_objective_and_runaway_configs_locked_to_level5() -> None:
    root = _repo_root()
    for pack in _PACKS:
        objectives_path = root / "campaigns" / pack / "omega_objectives_v1.json"
        runaway_path = root / "campaigns" / pack / "omega_runaway_config_v1.json"
        objectives = json.loads(objectives_path.read_text(encoding="utf-8"))
        runaway = json.loads(runaway_path.read_text(encoding="utf-8"))

        rows = objectives.get("metrics")
        assert isinstance(rows, list)
        assert len(rows) == 3
        assert {str(row.get("metric_id", "")) for row in rows if isinstance(row, dict)} == _OBJECTIVE_IDS
        for row in rows:
            assert isinstance(row, dict)
            assert str(row.get("direction", "")) == "MAXIMIZE"

        assert bool(runaway.get("enabled", False)) is True
        assert int(runaway.get("max_escalation_level_u64", 0)) == 5
        min_improve = runaway.get("min_improve_delta_q32")
        route_table = runaway.get("per_metric_route_table")
        assert isinstance(min_improve, dict)
        assert isinstance(route_table, dict)
        assert set(str(key) for key in min_improve.keys()) == _OBJECTIVE_IDS
        assert set(str(key) for key in route_table.keys()) == _OBJECTIVE_IDS
