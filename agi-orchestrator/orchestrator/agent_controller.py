"""Deterministic agent controller loop for plan construction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blake3 import blake3

from orchestrator.agent_transcript import AgentTranscript
from orchestrator.ledger_view import LedgerView
from orchestrator.plan_skill import PlanStep, build_plan_skill


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    concept: str
    domain: str
    inputs: dict[str, Any]
    allowed_tools: list[str]
    max_steps: int
    tool_sequence: list[str] | None = None


@dataclass(frozen=True)
class AgentResult:
    status: str
    plan_id: str
    plan_path: Path
    transcript_path: Path


def agent_solve(
    *,
    root_dir: Path,
    run_dir: Path,
    task: AgentTask,
    rng_seed: int,
    counterexamples: list[dict] | None = None,
) -> AgentResult:
    del rng_seed
    run_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = run_dir / "agent_transcript.jsonl"
    transcript = AgentTranscript(transcript_path)
    ledger = LedgerView(root_dir)

    skill_symbol = _resolve_skill(ledger, task.concept)
    steps: list[PlanStep] = []
    dependencies: list[str] = []

    if task.tool_sequence:
        for idx, tool in enumerate(task.tool_sequence):
            steps.append(
                PlanStep(
                    step_idx=idx,
                    kind="tool",
                    name=tool,
                    args={"step": idx},
                )
            )
    elif skill_symbol:
        dependencies.append(skill_symbol)
        steps.append(
            PlanStep(
                step_idx=0,
                kind="skill",
                name=skill_symbol,
                args={"inputs": task.inputs},
            )
        )
    elif task.allowed_tools:
        tool = sorted(task.allowed_tools)[0]
        steps.append(
            PlanStep(
                step_idx=0,
                kind="tool",
                name=tool,
                args=task.inputs,
            )
        )

    if counterexamples:
        steps.append(
            PlanStep(
                step_idx=len(steps),
                kind="repair",
                name="counterexample_adjustment",
                args={"examples": _stable_counterexamples(counterexamples)},
            )
        )

    event_hashes = []
    event_hashes.append(
        transcript.record(
            kind="plan_created",
            payload={"task_id": task.task_id, "steps": [step.__dict__ for step in steps]},
        )
    )
    for step in steps:
        event_hashes.append(transcript.record(kind="plan_step", payload=step.__dict__))

    trace_hash = _trace_hash(event_hashes)
    plan = build_plan_skill(
        task_id=task.task_id,
        steps=steps,
        dependencies=dependencies,
        constraints={
            "max_steps": task.max_steps,
            "allowed_tools": sorted(task.allowed_tools),
            "domain": task.domain,
            "concept": task.concept,
        },
        example_traces=[{"trace_hash": trace_hash, "event_hashes": event_hashes}],
    )
    plan_dir = run_dir / "plan_skills"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / f"{plan['plan_id']}.json"
    plan_path.write_text(
        json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    library_dir = root_dir / "plan_skills"
    library_dir.mkdir(parents=True, exist_ok=True)
    library_path = library_dir / f"{plan['plan_id']}.json"
    if not library_path.exists():
        library_path.write_text(
            json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    transcript.record(kind="plan_saved", payload={"plan_id": plan["plan_id"]})
    return AgentResult(
        status="success" if steps else "no_plan",
        plan_id=plan["plan_id"],
        plan_path=plan_path,
        transcript_path=transcript_path,
    )


def _resolve_skill(ledger: LedgerView, concept: str) -> str | None:
    symbols = ledger.get_symbols_for_concept(concept, limit=1)
    if symbols:
        return symbols[0].name
    return None


def _stable_counterexamples(counterexamples: list[dict]) -> list[dict]:
    rows = list(counterexamples)
    rows.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return rows


def _trace_hash(event_hashes: list[str]) -> str:
    canonical = json.dumps(event_hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return blake3(canonical.encode("utf-8")).hexdigest()
