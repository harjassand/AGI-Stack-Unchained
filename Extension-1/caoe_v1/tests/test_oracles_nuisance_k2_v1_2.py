from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
CDEL_ROOT = REPO_ROOT / "CDEL-v2"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CDEL_ROOT))

from tools.solve_regime_oracle_depth2_v1 import solve as solve_depth2  # noqa: E402
from tools.solve_regime_oracle_memoryless_v1 import solve as solve_memoryless  # noqa: E402
from tools.solve_regime_oracle_sequence_v1 import solve as solve_sequence  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _suitepack() -> dict:
    return {
        "format": "caoe_suitepack_v1",
        "schema_version": 1,
        "suite_id": "suite_dev",
        "target_env_id": "switchboard_v1",
        "regimes": [
            {
                "regime_id": "nuisance_k2_00",
                "shift_family": "nuisance_rate_scale",
                "perm": list(range(20)),
                "mask": [0] * 20,
            }
        ],
        "shift_families": [{"family_id": "nuisance_rate_scale", "regime_ids": ["nuisance_k2_00"]}],
        "episodes": [
            {
                "episode_id": "nuisance_k2_00_ep0",
                "regime_id": "nuisance_k2_00",
                "goal": {"x0": 1},
                "max_steps": 2,
                "initial_x": [0, 0, 0, 0],
                "initial_n": [0] * 16,
            }
        ],
    }


def test_oracles_nuisance_k2_v1_2(tmp_path: Path) -> None:
    suitepack_path = tmp_path / "suitepack.json"
    _write_json(suitepack_path, _suitepack())

    seq = solve_sequence(
        suitepack_path=suitepack_path,
        regime_id="nuisance_k2_00",
        seed=123,
        horizon=2,
        episode_id=None,
    )
    mem = solve_memoryless(
        suitepack_path=suitepack_path,
        regime_id="nuisance_k2_00",
        seed=123,
        horizon=2,
        episode_id=None,
    )
    depth2 = solve_depth2(
        suitepack_path=suitepack_path,
        regime_id="nuisance_k2_00",
        seed=123,
        horizon=2,
        episode_id=None,
    )

    assert seq["schema"] == "solve_regime_oracle_sequence_v1"
    assert mem["schema"] == "solve_regime_oracle_memoryless_v1"
    assert depth2["schema"] == "solve_regime_oracle_depth2_v1"
    assert seq["found"] is True
    assert mem["found"] is True
    assert depth2["found"] is True
