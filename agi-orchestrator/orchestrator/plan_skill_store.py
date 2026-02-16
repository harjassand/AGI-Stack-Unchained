"""Plan skill loading and deterministic selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_plan_skills(root_dir: Path) -> list[dict[str, Any]]:
    plan_dir = root_dir / "plan_skills"
    if not plan_dir.exists():
        return []
    skills: list[dict[str, Any]] = []
    for path in sorted(plan_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("artifact") != "plan_skill.v1":
            continue
        plan_id = payload.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            continue
        payload = dict(payload)
        payload["path"] = str(path)
        skills.append(payload)
    skills.sort(key=lambda item: str(item.get("plan_id")))
    return skills


def select_plan_skill(
    plan_skills: list[dict[str, Any]], *, concept: str, domain: str
) -> tuple[dict[str, Any] | None, list[str]]:
    considered = [str(item.get("plan_id")) for item in plan_skills if item.get("plan_id")]
    considered = sorted(set(considered))
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for skill in plan_skills:
        plan_id = skill.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            continue
        constraints = skill.get("constraints")
        if not isinstance(constraints, dict):
            continue
        plan_concept = constraints.get("concept")
        plan_domain = constraints.get("domain")
        score = None
        if plan_concept == concept:
            score = 0
        elif plan_domain == domain:
            score = 1
        if score is None:
            continue
        candidates.append((score, plan_id, skill))
    if not candidates:
        return None, considered
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2], considered
