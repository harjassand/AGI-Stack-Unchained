from __future__ import annotations

import json
from pathlib import Path

from orchestrator.proposer.agent import AgentProposer
from orchestrator.types import ContextBundle


def _write_plan_skill(path: Path, *, plan_id: str, domain: str, concept: str) -> None:
    payload = {
        "artifact": "plan_skill.v1",
        "plan_id": plan_id,
        "task_id": concept,
        "steps": [],
        "dependencies": [],
        "constraints": {"domain": domain, "concept": concept},
        "example_traces": [],
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _write_env_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[sealed]",
                "eval_harness_id = \"env-harness-v1\"",
                "eval_harness_hash = \"env-harness-v1-hash\"",
                "eval_suite_hash = \"deadbeef\"",
                "episodes = 1",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_env_agent_fallback_when_plan_skill_fails(tmp_path: Path) -> None:
    plan_dir = tmp_path / "plan_skills"
    plan_dir.mkdir()
    _write_plan_skill(plan_dir / "plan.json", plan_id="plan-1", domain="env", concept="gridworld")
    config_path = tmp_path / "env_dev.toml"
    _write_env_config(config_path)

    proposer = AgentProposer(root_dir=tmp_path, config_path=config_path, run_dir=tmp_path / "run")
    bundle = ContextBundle(
        concept="gridworld",
        baseline_symbol="policy_base",
        oracle_symbol="policy_oracle",
        type_norm="Int->Int->Int->Int->Int",
        symbols=[],
    )
    candidates = proposer.propose(context=bundle, budget=1, rng_seed=11)
    assert candidates
    candidate = candidates[0]
    assert candidate.payload.get("declared_deps") == ["policy_oracle"]
    assert candidate.meta is not None
    assert candidate.meta.get("plan_skill_used") is False
    assert candidate.meta.get("wrapped") == "policy_oracle"
