from __future__ import annotations

from pathlib import Path

from tools.mission_control import mission_pipeline_v1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _valid_mission_request() -> dict:
    return {
        "schema_name": "mission_request_v1",
        "schema_version": "v19_0",
        "user_prompt": "Build a deterministic mission evidence report.",
        "domain": "general",
        "success_spec": {
            "definition_of_done": "mission executes end-to-end",
            "pinned_eval_refs": [
                {
                    "suitepack_id": "suitepack_demo_v1",
                    "heldout_b": True,
                    "gate": {"metric": "score", "op": ">=", "threshold_q32": 0},
                }
            ],
            "deliverables": ["evidence_pack"],
        },
    }


def test_compile_execute_pack_and_replay_verify_passes() -> None:
    result = mission_pipeline_v1.run_compile_execute_and_pack(
        _valid_mission_request(),
        repo_root=_repo_root(),
        max_ticks_u64=16,
        dev_mode=True,
    )
    assert result["ok_b"] is True
    assert str(result["mission_id"]).startswith("sha256:")
    assert result["state"]["status"] == "SUCCEEDED"
    assert isinstance(result["evidence_pack_id"], str)
    assert result["evidence_pack_id"].startswith("sha256:")
    assert result["replay_verify"]["ok_b"] is True
    assert result["replay_verify"]["reason_code"] == "PASS"


def test_compile_fails_closed_when_clarification_required() -> None:
    mission_request = {
        "schema_name": "mission_request_v1",
        "schema_version": "v19_0",
        "user_prompt": "Do complex task with no success spec.",
        "domain": "general",
    }
    compiled = mission_pipeline_v1.compile_mission(mission_request, repo_root=_repo_root())
    receipt = compiled["compile_receipt"]
    assert receipt["ok_b"] is False
    assert receipt["reason_code"] == "NEEDS_CLARIFICATION"
    assert len(receipt["required_clarifications"]) >= 1
