from __future__ import annotations

import json
from pathlib import Path

from tools.polymath.polymath_void_to_goals_v1 import inject_void_goals


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")


def test_void_to_goals_injects_top_ranked_deterministically(tmp_path: Path) -> None:
    void_path = tmp_path / "void.jsonl"
    queue_path = tmp_path / "goals" / "omega_goal_queue_effective_v1.json"
    router_path = tmp_path / "void_topic_router_v1.json"

    _write_json(
        router_path,
        {
            "schema_version": "void_topic_router_v1",
            "default_route": "SCIENCE",
            "topic_overrides": {},
            "keyword_rules": [
                {"route": "MATH", "contains_any": ["math", "algebra", "proof"]},
                {"route": "SCIENCE", "contains_any": ["physics", "chemistry", "biology"]},
            ],
        },
    )
    _write_jsonl(
        void_path,
        [
            {"topic_id": "topic:physics", "topic_name": "Physics", "void_score_q32": {"q": 90}},
            {"topic_id": "topic:algebra", "topic_name": "Algebraic geometry", "void_score_q32": {"q": 100}},
            {"topic_id": "topic:biology", "topic_name": "Biology", "void_score_q32": {"q": 10}},
        ],
    )
    _write_json(queue_path, {"schema_version": "omega_goal_queue_v1", "goals": []})

    report = inject_void_goals(
        void_report_path=void_path,
        out_goal_queue_effective_path=queue_path,
        router_path=router_path,
        max_goals=2,
        tick_u64=37,
    )

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    goals = queue.get("goals")
    assert isinstance(goals, list)
    assert report["goals_injected_u64"] == 2
    assert goals[0]["goal_id"] == "goal_auto_00_void_math_topic_algebra_0037"
    assert goals[0]["capability_id"] == "RSI_BOUNDLESS_MATH_V8"
    assert goals[1]["goal_id"] == "goal_auto_00_void_science_topic_physics_0037"
    assert goals[1]["capability_id"] == "RSI_BOUNDLESS_SCIENCE_V9"


def test_void_to_goals_skips_existing_pending_topic(tmp_path: Path) -> None:
    void_path = tmp_path / "void.jsonl"
    queue_path = tmp_path / "goals" / "omega_goal_queue_effective_v1.json"
    router_path = tmp_path / "void_topic_router_v1.json"

    _write_json(
        router_path,
        {
            "schema_version": "void_topic_router_v1",
            "default_route": "SCIENCE",
            "topic_overrides": {"topic:math": "MATH"},
            "keyword_rules": [],
        },
    )
    _write_jsonl(
        void_path,
        [
            {"topic_id": "topic:math", "topic_name": "Math", "void_score_q32": {"q": 10}},
            {"topic_id": "topic:chemistry", "topic_name": "Chemistry", "void_score_q32": {"q": 9}},
        ],
    )
    _write_json(
        queue_path,
        {
            "schema_version": "omega_goal_queue_v1",
            "goals": [
                {
                    "goal_id": "goal_auto_00_void_math_topic_math_0001",
                    "capability_id": "RSI_BOUNDLESS_MATH_V8",
                    "status": "PENDING",
                }
            ],
        },
    )

    report = inject_void_goals(
        void_report_path=void_path,
        out_goal_queue_effective_path=queue_path,
        router_path=router_path,
        max_goals=2,
        tick_u64=2,
    )

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    goals = queue.get("goals")
    assert isinstance(goals, list)
    assert report["goals_injected_u64"] == 1
    assert len(goals) == 2
    assert goals[1]["goal_id"] == "goal_auto_00_void_science_topic_chemistry_0002"
