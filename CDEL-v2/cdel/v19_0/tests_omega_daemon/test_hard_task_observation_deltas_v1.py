from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0 import omega_promoter_v1 as promoter


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_observation(obs_dir: Path, payload: dict[str, object]) -> str:
    digest = canon_hash_obj(payload)
    hex_part = digest.split(":", 1)[1]
    _write_canon(obs_dir / f"sha256_{hex_part}.omega_observation_report_v1.json", payload)
    return digest


def _observation_payload(
    *,
    tick_u64: int,
    code_q32: int,
    perf_q32: int,
    reasoning_q32: int,
    suite_q32: int,
) -> dict[str, object]:
    return {
        "schema_version": "omega_observation_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "active_manifest_hash": "sha256:" + ("1" * 64),
        "metrics": {
            "hard_task_code_correctness_q32": {"q": int(code_q32)},
            "hard_task_performance_q32": {"q": int(perf_q32)},
            "hard_task_reasoning_q32": {"q": int(reasoning_q32)},
            "hard_task_suite_score_q32": {"q": int(suite_q32)},
        },
        "sources": [],
        "inputs_hashes": {
            "policy_hash": "sha256:" + ("2" * 64),
            "registry_hash": "sha256:" + ("3" * 64),
            "objectives_hash": "sha256:" + ("4" * 64),
        },
    }


def test_hard_task_observation_deltas_counts_positive_metric_gains(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    obs_dir = state_root / "observations"
    _write_observation(
        obs_dir,
        _observation_payload(
            tick_u64=9,
            code_q32=100,
            perf_q32=200,
            reasoning_q32=300,
            suite_q32=200,
        ),
    )
    latest_hash = _write_observation(
        obs_dir,
        _observation_payload(
            tick_u64=10,
            code_q32=120,
            perf_q32=180,
            reasoning_q32=340,
            suite_q32=220,
        ),
    )

    deltas = promoter._hard_task_observation_deltas({"state_root": str(state_root)})
    assert deltas["observation_hash"] == latest_hash
    assert int(deltas["gain_count_u64"]) == 3
    delta_by_metric = deltas["delta_by_metric"]
    assert isinstance(delta_by_metric, dict)
    assert int(delta_by_metric["hard_task_code_correctness_q32"]) == 20
    assert int(delta_by_metric["hard_task_performance_q32"]) == -20
    assert int(delta_by_metric["hard_task_reasoning_q32"]) == 40
    assert int(delta_by_metric["hard_task_suite_score_q32"]) == 20
