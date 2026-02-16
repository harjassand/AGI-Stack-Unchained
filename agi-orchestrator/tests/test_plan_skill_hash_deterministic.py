from __future__ import annotations

from orchestrator.plan_skill import PlanStep, build_plan_skill, plan_skill_hash


def test_plan_skill_hash_deterministic() -> None:
    steps = [
        PlanStep(step_idx=0, kind="tool", name="read_file", args={"path": "input.json"}),
        PlanStep(step_idx=1, kind="skill", name="algo.is_even", args={"n": 2}),
    ]
    payload = build_plan_skill(
        task_id="tooluse.file_transform",
        steps=steps,
        dependencies=["algo.is_even"],
        constraints={"max_steps": 5},
        example_traces=[{"trace_hash": "abc", "steps": 2}],
    )
    payload2 = build_plan_skill(
        task_id="tooluse.file_transform",
        steps=steps,
        dependencies=["algo.is_even"],
        constraints={"max_steps": 5},
        example_traces=[{"trace_hash": "abc", "steps": 2}],
    )
    assert payload["plan_id"] == payload2["plan_id"]
    assert payload["plan_id"] == plan_skill_hash(payload)
