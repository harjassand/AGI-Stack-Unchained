"""Plan skill artifacts and deterministic hashing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from blake3 import blake3


@dataclass(frozen=True)
class PlanStep:
    step_idx: int
    kind: str
    name: str
    args: dict[str, Any]


def build_plan_skill(
    *,
    task_id: str,
    steps: Iterable[PlanStep],
    dependencies: list[str],
    constraints: dict[str, Any],
    example_traces: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "artifact": "plan_skill.v1",
        "task_id": task_id,
        "steps": [step.__dict__ for step in steps],
        "dependencies": sorted(set(dependencies)),
        "constraints": constraints,
        "example_traces": example_traces,
    }
    plan_id = plan_skill_hash(payload)
    return {
        "artifact": "plan_skill.v1",
        "plan_id": plan_id,
        "task_id": task_id,
        "steps": payload["steps"],
        "dependencies": payload["dependencies"],
        "constraints": constraints,
        "example_traces": example_traces,
    }


def plan_skill_hash(payload: dict[str, Any]) -> str:
    normalized = {
        "artifact": payload.get("artifact"),
        "task_id": payload.get("task_id"),
        "steps": payload.get("steps"),
        "dependencies": payload.get("dependencies"),
        "constraints": payload.get("constraints"),
        "example_traces": payload.get("example_traces"),
    }
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return blake3(canonical.encode("utf-8")).hexdigest()
