"""Agent-based proposer that converts plan skills into policies."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cdel.config import load_config_from_path
from cdel.sealed.config import load_sealed_config

from orchestrator.agent_controller import AgentTask, agent_solve
from orchestrator.agent_policy import tooluse_policy_payload, wrapper_policy_payload
from orchestrator.plan_skill_store import load_plan_skills, select_plan_skill
from orchestrator.plan_skill import PlanStep
from orchestrator.proposer.base import Proposer
from orchestrator.types import Candidate, ContextBundle


@dataclass(frozen=True)
class AgentProposer(Proposer):
    root_dir: Path
    config_path: Path
    run_dir: Path

    def propose(self, *, context: ContextBundle, budget: int, rng_seed: int) -> list[Candidate]:
        if budget <= 0:
            return []
        cfg = load_config_from_path(self.root_dir, self.config_path)
        sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
        harness_id = sealed_cfg.eval_harness_id
        if harness_id == "tooluse-harness-v1":
            tool_sequence, allowed_tools, max_steps = _load_tool_sequence(
                root_dir=self.root_dir, cfg_data=cfg.data
            )
            if not tool_sequence:
                return []
            task = AgentTask(
                task_id=context.concept,
                concept=context.concept,
                domain="tooluse",
                inputs={},
                allowed_tools=allowed_tools,
                max_steps=max_steps,
                tool_sequence=tool_sequence,
            )
            agent_run_dir = self.run_dir / "agent"
            result = agent_solve(
                root_dir=self.root_dir,
                run_dir=agent_run_dir,
                task=task,
                rng_seed=rng_seed,
            )
            plan = json.loads(result.plan_path.read_text(encoding="utf-8"))
            steps = [PlanStep(**step) for step in plan.get("steps", [])]
            actions = list(range(len([s for s in steps if s.kind == "tool"])))
            name = f"{context.concept}_agent_{rng_seed}"
            payload = tooluse_policy_payload(name=name, concept=context.concept, action_sequence=actions)
            return [Candidate(name=name, payload=payload, proposer="agent", meta={"plan_id": result.plan_id})]

        if harness_id == "env-harness-v1":
            name = f"{context.concept}_agent_{rng_seed}"
            plan_skills = load_plan_skills(self.root_dir)
            selected, considered = select_plan_skill(
                plan_skills, concept=context.concept, domain="env"
            )
            target_symbol = context.oracle_symbol
            selected_id = None
            used_plan_skill = False
            if selected:
                selected_id = selected.get("plan_id")
                deps = selected.get("dependencies") or []
                if isinstance(deps, list) and deps:
                    target_symbol = str(deps[0])
                    used_plan_skill = True
            payload = wrapper_policy_payload(
                name=name,
                concept=context.concept,
                target_symbol=target_symbol,
                type_norm=context.type_norm,
            )
            meta = {
                "wrapped": target_symbol,
                "plan_skill_considered": considered,
                "plan_skill_selected": selected_id,
                "plan_skill_used": used_plan_skill,
            }
            return [Candidate(name=name, payload=payload, proposer="agent", meta=meta)]

        return []


def _load_tool_sequence(*, root_dir: Path, cfg_data: dict) -> tuple[list[str], list[str], int]:
    sealed = cfg_data.get("sealed") or {}
    suite_hash = sealed.get("eval_suite_hash")
    max_steps = 2
    if not isinstance(suite_hash, str) or not suite_hash:
        return [], [], int(max_steps or 2)
    suites_dir = os.environ.get("CDEL_SUITES_DIR")
    if suites_dir:
        suite_path = Path(suites_dir) / f"{suite_hash}.jsonl"
    else:
        suite_path = root_dir / "sealed_suites" / f"{suite_hash}.jsonl"
    if not suite_path.exists():
        return [], [], int(max_steps or 2)
    first_row = None
    for line in suite_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        first_row = json.loads(line)
        break
    if not isinstance(first_row, dict):
        return [], [], int(max_steps or 2)
    tool_calls = first_row.get("tool_calls", [])
    allowed_tools = first_row.get("allowed_tools", [])
    if isinstance(first_row.get("max_steps"), int):
        max_steps = int(first_row["max_steps"])
    if not isinstance(tool_calls, list) or not isinstance(allowed_tools, list):
        return [], [], int(max_steps or 2)
    tool_sequence = []
    for call in tool_calls:
        if isinstance(call, dict) and isinstance(call.get("tool"), str):
            tool_sequence.append(call["tool"])
    return tool_sequence, [str(tool) for tool in allowed_tools], int(max_steps or 2)
